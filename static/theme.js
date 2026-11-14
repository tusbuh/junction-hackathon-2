// DESIGN3: optional visual themes. ?theme=a (blueprint night) or ?theme=b (paper editorial).
// No param = the original look, untouched. Pure presentation: no feature, route or number changes.
(function () {
  var t = (new URLSearchParams(location.search).get('theme') || '').toLowerCase();
  if (t !== 'a' && t !== 'b') return;
  var root = document.documentElement;
  root.classList.add('themed', 'theme-' + t);
  var head = document.head || document.getElementsByTagName('head')[0];
  var fonts = document.createElement('link'); fonts.rel = 'stylesheet'; fonts.href = '/static/fonts/fonts.css';
  var css = document.createElement('link'); css.rel = 'stylesheet'; css.id = 'themeCss'; css.href = '/static/theme-' + t + '.css';
  head.appendChild(fonts); head.appendChild(css);
  // feature scripts append their own stylesheets later (wow.css, audit.css, race.css): keep the theme last
  new MutationObserver(function () { if (head.lastElementChild !== css) head.appendChild(css); })
    .observe(head, { childList: true });

  // Buttons: drop the emoji / pictogram prefixes ("🚶 Walk in 3D" -> "Walk in 3D"); the words stay identical.
  var GLYPH = /^[\s←-⯿⌀-⏿■-◿☀-➿️€]*(?:\uD83C[\uDC00-\uDFFF]|\uD83D[\uDC00-\uDFFF]|\uD83E[\uDD00-\uDFFF])?[️‍\s]*/;
  function clean(btn) {
    if (btn.dataset.tc) return; btn.dataset.tc = '1';
    for (var n = btn.firstChild; n; n = n.nextSibling) {
      if (n.nodeType === 3 && n.nodeValue.trim()) { var v = n.nodeValue.replace(GLYPH, ''); if (v.trim()) n.nodeValue = v; break; }
      if (n.nodeType === 1 && !/^(B|SPAN|I|KBD)$/.test(n.tagName)) break;
    }
  }
  function sweep() {
    document.querySelectorAll('.top .tbtn, .top .wowBtn, .splash .cta button, #auditBtn, .wkAuto').forEach(clean);
  }
  var k = 0, iv = setInterval(function () { sweep(); if (++k > 40) clearInterval(iv); }, 250);
  document.addEventListener('DOMContentLoaded', sweep);
})();
