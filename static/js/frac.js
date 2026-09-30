/* عرض الكسور بصيغة رياضية: 3/8 تصبح البسط فوق المقام.
   يدعم: 3/8 ، 2x/3 ، x/2 ، (x+1)/(x-2) ، \frac{a}{b}
   ولا يلمس الوحدات (km/h ، m/s) ولا التواريخ (12/05/2026). */
(function () {
  var TOKEN = '(?:\\([^()\\n]{1,40}\\)|-?\\d+(?:[.,]\\d+)?[a-zA-Z]?|[a-zA-Z])';
  var RE = new RegExp('\\\\frac\\{([^{}]{1,40})\\}\\{([^{}]{1,40})\\}|(^|[^\\w/.,)])(' + TOKEN + ')\\s*/\\s*(' + TOKEN + ')(?![\\w/(])', 'g');

  function strip(s) { return /^\(.*\)$/.test(s) ? s.slice(1, -1) : s; }
  function isFraction(num, den) {
    // حرف/حرف مثل km/h أو a/b قد يكون وحدة: نشترط رقماً أو قوساً في أحد الطرفين
    return /[\d(]/.test(num) || /[\d(]/.test(den);
  }
  function makeFrac(num, den) {
    var f = document.createElement('span');
    f.className = 'frac';
    f.setAttribute('dir', 'ltr');
    var n = document.createElement('span'); n.className = 'num'; n.textContent = strip(num);
    var d = document.createElement('span'); d.className = 'den'; d.textContent = strip(den);
    var sr = document.createElement('span'); sr.className = 'frac-sr'; sr.textContent = num + '/' + den;
    f.appendChild(n); f.appendChild(d); f.appendChild(sr);
    return f;
  }
  var GAP = /^[\s\d+\-−×÷*=.,:<>≤≥]*$/;          // ما بين كسرين في نفس العبارة الرياضية
  var TAIL = /^[\s]*(?:[+\-−×÷*=<>≤≥]\s*-?\d+(?:[.,]\d+)?(?![\d.,]|\s*\/)\s*)+/;
  function processText(node) {
    var text = node.nodeValue, last = 0, m, frag = null, group = null;
    RE.lastIndex = 0;
    while ((m = RE.exec(text))) {
      var num, den, start = m.index, pre = '';
      if (m[1] !== undefined) { num = m[1]; den = m[2]; }
      else { pre = m[3]; num = m[4]; den = m[5]; if (!isFraction(num, den)) continue; }
      frag = frag || document.createDocumentFragment();
      var gap = text.slice(last, start) + pre, sign = '';
      if (num.charAt(0) === '-') { sign = '−'; num = num.slice(1); }
      if (group && GAP.test(gap)) {
        group.appendChild(document.createTextNode(gap + sign));
      } else {
        frag.appendChild(document.createTextNode(gap));
        // العبارة الرياضية تُقرأ دائماً من اليسار لليمين حتى داخل نص عربي
        group = document.createElement('span');
        group.className = 'math-run'; group.setAttribute('dir', 'ltr');
        if (sign) group.appendChild(document.createTextNode(sign));
        frag.appendChild(group);
      }
      group.appendChild(makeFrac(num, den));
      last = RE.lastIndex;
      var t = TAIL.exec(text.slice(last));
      if (t) { group.appendChild(document.createTextNode(t[0].replace(/\s+$/, ''))); last += t[0].replace(/\s+$/, '').length; }
      RE.lastIndex = last;
    }
    if (!frag) return;
    frag.appendChild(document.createTextNode(text.slice(last)));
    node.parentNode.replaceChild(frag, node);
  }
  function render(root) {
    (root || document).querySelectorAll('.q-text, .c-text, .math').forEach(function (el) {
      var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null), nodes = [], n;
      while ((n = walker.nextNode())) if (!n.parentNode.closest('.frac')) nodes.push(n);
      nodes.forEach(processText);
    });
  }
  window.renderFractions = render;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { render(); });
  else render();
})();
