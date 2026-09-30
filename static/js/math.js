/* عرض الرموز الرياضية في نص الأسئلة والخيارات:
   - الكسور: 3/8 ، 2x/3 ، (x+1)/(x-2) ، 1/√2 ، √2/2 ، \frac{a}{b}  => البسط فوق المقام
   - الجذر: √18 ، 5√2 ، √(x+1)  => خط الجذر يمتد فوق كل ما تحته
   - الأشعة: AB⃗ (حرف + سهم مركّب U+20D7) أو vec(AB)  => سهم فوق الحروف
   لا يلمس الوحدات (km/h ، m/s) ولا التواريخ (12/05/2026)، وكل رمز آخر يبقى كما هو. */
(function () {
  var atoms = [];
  var BASE = 0xE000;                        // محارف خاصة تحجز مكان كل رمز مركّب
  var P = '[\\uE000-\\uF8FF]';
  function atom(html) { atoms.push(html); return String.fromCharCode(BASE + atoms.length - 1); }
  function esc(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  function strip(s) { return /^\(.*\)$/.test(s) ? s.slice(1, -1) : s; }

  var VEC = /(?:vec\(([^()]{1,6})\)|([A-Za-z0-9]{1,3}|[A-Za-z]'?)[⃯⃮⃗⃑])/g;
  var SQRT = new RegExp('√\\s*(\\([^()]{1,40}\\)|\\d+(?:[.,]\\d+)?[a-zA-Z]?|[a-zA-Z]|' + P + ')', 'g');
  var TOKEN = '(?:\\([^()\\n]{1,40}\\)|-?\\d+(?:[.,]\\d+)?(?:π|[a-zA-Z])?' + P + '?|(?:π|[a-zA-Z])' + P + '?|' + P + ')';
  var FRAC = new RegExp('\\\\frac\\{([^{}]{1,40})\\}\\{([^{}]{1,40})\\}|(^|[^\\w/.,)])(' + TOKEN + ')\\s*/\\s*(' + TOKEN + ')(?![\\w/(])', 'g');
  var GAP = /^[\s\d+\-−×÷*=.,:<>≤≥]*$/;
  var TAIL = new RegExp('^\\s*(?:[+\\-−×÷*=<>≤≥]\\s*-?\\d*(?:[.,]\\d+)?' + P + '?(?![\\d.,]|\\s*\\/)\\s*)+');

  function fracHtml(num, den) {
    return '<span class="frac" dir="ltr"><span class="num">' + strip(num) + '</span><span class="den">' +
      strip(den) + '</span></span>';
  }

  function convert(text) {
    atoms = [];
    var s = esc(text), changed = false;
    s = s.replace(VEC, function (m, a, b) {
      changed = true;
      return atom('<span class="vec" dir="ltr">' + (a || b) + '</span>');
    });
    s = s.replace(SQRT, function (m, r) {
      changed = true;
      return atom('<span class="sqrt" dir="ltr"><span class="rad">√</span><span class="rc">' + strip(r) + '</span></span>');
    });
    // الكسور، مع جمع العبارة الرياضية الواحدة في مقطع يُقرأ من اليسار لليمين
    var out = '', last = 0, m, open = false;
    FRAC.lastIndex = 0;
    while ((m = FRAC.exec(s))) {
      var num, den, pre = '';
      if (m[1] !== undefined) { num = m[1]; den = m[2]; }
      else {
        pre = m[3]; num = m[4]; den = m[5];
        if (!/[\d(-]/.test(num + den)) continue;   // km/h ، a/b : وحدات
      }
      changed = true;
      var gap = s.slice(last, m.index) + pre, sign = '';
      if (num.charAt(0) === '-') { sign = '−'; num = num.slice(1); }
      if (open && GAP.test(gap)) out += gap + sign;
      else {
        if (open) out += '</span>';
        out += gap + '<span class="math-run" dir="ltr">' + sign;
        open = true;
      }
      out += fracHtml(num, den);
      last = FRAC.lastIndex;
      var t = TAIL.exec(s.slice(last));
      if (t) { var tt = t[0].replace(/\s+$/, ''); out += tt; last += tt.length; }
      FRAC.lastIndex = last;
    }
    if (open) out += '</span>';
    s = out + s.slice(last);
    if (!changed) return null;
    // استبدال المحارف المحجوزة بالرموز (قد تكون متداخلة: جذر داخل كسر)
    var re = new RegExp(P, 'g');
    for (var i = 0; i < 5 && re.test(s); i++) {
      s = s.replace(re, function (c) { return atoms[c.charCodeAt(0) - BASE] || c; });
    }
    // أي شيء قبل الكسر أو الجذر مثل 5√2 يبقى ملاصقاً له
    return s;
  }

  var SKIP = '.frac, .sqrt, .vec, .math-run, .letter, .q-head, .q-num, .badge, .tag, button, a, script, style, textarea, input, select';
  function render(root) {
    (root || document).querySelectorAll('.q-text, .c-text, .math, .choice, .question').forEach(function (el) {
      var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null), nodes = [], n;
      while ((n = walker.nextNode())) {
        if (n.parentNode.closest(SKIP)) continue;
        nodes.push(n);
      }
      nodes.forEach(function (node) {
        if (!node.parentNode || /[\uE000-\uF8FF]/.test(node.nodeValue)) return;
        var html = convert(node.nodeValue);
        if (html === null) return;
        var tpl = document.createElement('template');
        tpl.innerHTML = html;
        node.parentNode.replaceChild(tpl.content, node);
      });
    });
  }
  window.renderMath = render;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { render(); });
  else render();
})();
