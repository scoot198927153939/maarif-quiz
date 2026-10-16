/* وضع الامتحان المقفل: مؤقت، حفظ تلقائي، ورصد محاولات الخروج */
(function () {
  var form = document.getElementById('exam-form');
  if (!form) return;

  var csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
  var secondsLeft = parseInt(form.dataset.secondsLeft, 10);
  var violations = parseInt(form.dataset.violations, 10);
  var maxViolations = parseInt(form.dataset.maxViolations, 10);
  var submitting = false;
  var lastViolation = 0;
  var dialogOpen = false;
  var overlay = document.getElementById('lock-overlay');
  var lockMsg = document.getElementById('lock-msg');
  var timerEl = document.getElementById('timer');

  function post(url, data) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify(data || {}),
      credentials: 'same-origin',
      keepalive: true
    }).then(function (r) { return r.json(); });
  }

  function submitNow(auto) {
    if (submitting) return;
    submitting = true;
    document.getElementById('auto-field').value = auto ? '1' : '0';
    form.submit();
  }

  // ---------- المؤقت
  function tick() {
    if (secondsLeft <= 0) {
      timerEl.textContent = '00:00';
      submitNow(true);
      return;
    }
    var m = Math.floor(secondsLeft / 60), s = secondsLeft % 60;
    timerEl.textContent = (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
    timerEl.classList.toggle('danger', secondsLeft <= 60);
    secondsLeft--;
  }
  tick();
  setInterval(tick, 1000);

  // ---------- الحفظ التلقائي
  function updateProgress() {
    var total = form.querySelectorAll('.question').length;
    var answered = new Set();
    form.querySelectorAll('input[type=radio]:checked').forEach(function (i) { answered.add(i.name); });
    document.getElementById('progress').textContent = 'أجبت على ' + answered.size + ' من ' + total;
    return total - answered.size;
  }
  form.addEventListener('change', function (e) {
    var input = e.target;
    if (input.type !== 'radio') return;
    post(form.dataset.saveUrl, { question: input.dataset.question, selected: input.value })
      .then(function (res) { if (res.submitted) { submitting = true; location.reload(); } })
      .catch(function () {});
    updateProgress();
  });
  updateProgress();

  document.getElementById('submit-btn').addEventListener('click', function () {
    var left = updateProgress();
    var msg = left > 0 ? 'لم تُجب على ' + left + ' سؤال. هل تريد التسليم؟' : 'هل تريد تسليم الامتحان نهائياً؟';
    dialogOpen = true;
    var ok = confirm(msg);
    dialogOpen = false;
    lastViolation = Date.now(); // نافذة التأكيد قد تُطلق حدث blur، فلا نحسبه خروجاً
    if (ok) submitNow(false);
  });

  // ---------- ملء الشاشة
  function isFullscreen() {
    return !!(document.fullscreenElement || document.webkitFullscreenElement);
  }
  function enterFullscreen() {
    var el = document.documentElement;
    var fn = el.requestFullscreen || el.webkitRequestFullscreen;
    if (fn) { try { var p = fn.call(el); if (p && p.catch) p.catch(function () {}); } catch (e) {} }
  }
  function showOverlay(text) {
    lockMsg.textContent = text;
    overlay.classList.remove('hidden');
  }
  document.getElementById('resume-btn').addEventListener('click', function () {
    enterFullscreen();
    overlay.classList.add('hidden');
  });
  // عند التحميل لأول مرة (أو بعد إعادة تحميل الصفحة) نطلب ملء الشاشة بنقرة
  if (!isFullscreen() && document.fullscreenEnabled !== false) {
    showOverlay('اضغط الزر للدخول إلى وضع ملء الشاشة وبدء الإجابة.');
  }

  // ---------- رصد محاولات الخروج
  function violation(reason) {
    if (submitting || dialogOpen) return;
    var now = Date.now();
    if (now - lastViolation < 2000) return; // تجاهل الأحداث المتكررة لنفس الخروج
    lastViolation = now;
    post(form.dataset.violationUrl).then(function (res) {
      violations = res.violations || violations + 1;
      if (res.submitted) {
        submitting = true;
        alert('تجاوزت الحد المسموح به من محاولات الخروج. تم تسليم امتحانك تلقائياً.');
        location.href = location.href.replace(/take\/?$/, 'result/');
        return;
      }
      showOverlay(reason + ' تم تسجيل محاولة خروج (' + violations + ' من ' + maxViolations +
        '). عند بلوغ ' + maxViolations + ' يُسلَّم امتحانك تلقائياً.');
    }).catch(function () {
      showOverlay(reason + ' تم تسجيل محاولة خروج.');
    });
  }

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) violation('غادرت صفحة الامتحان.');
  });
  window.addEventListener('blur', function () { violation('غيّرت النافذة.'); });
  ['fullscreenchange', 'webkitfullscreenchange'].forEach(function (ev) {
    document.addEventListener(ev, function () {
      if (!isFullscreen() && !submitting) violation('خرجت من وضع ملء الشاشة.');
    });
  });

  // ---------- منع النسخ والقائمة واختصارات لوحة المفاتيح
  ['contextmenu', 'copy', 'cut', 'paste', 'selectstart', 'dragstart'].forEach(function (ev) {
    document.addEventListener(ev, function (e) { e.preventDefault(); });
  });
  document.addEventListener('keydown', function (e) {
    var k = (e.key || '').toLowerCase();
    var blocked =
      k === 'f12' || k === 'f5' || k === 'printscreen' || k === 'escape' ||
      (e.ctrlKey || e.metaKey) && ['c', 'v', 'x', 'a', 'p', 's', 'u', 'r', 't', 'n', 'w', 'f', 'tab'].indexOf(k) >= 0 ||
      (e.ctrlKey && e.shiftKey && ['i', 'j', 'c'].indexOf(k) >= 0) ||
      (e.altKey && (k === 'tab' || k === 'arrowleft' || k === 'arrowright'));
    if (blocked) { e.preventDefault(); e.stopPropagation(); }
  }, true);

  // منع زر الرجوع في المتصفح
  history.pushState(null, '', location.href);
  window.addEventListener('popstate', function () {
    history.pushState(null, '', location.href);
    violation('حاولت الرجوع إلى صفحة أخرى.');
  });

  // تحذير عند محاولة إغلاق الصفحة أو تحديثها
  window.addEventListener('beforeunload', function (e) {
    if (!submitting) { e.preventDefault(); e.returnValue = ''; }
  });
})();
