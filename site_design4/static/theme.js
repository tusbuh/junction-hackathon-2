// DESIGN4: "pro" theme is the default (works with ?static=1). Pass ?theme=classic for the original look.
// Pure presentation: every button keeps its id, handler, shortcut and route; secondary tools move into one Tools menu.
(function () {
  var t = (new URLSearchParams(location.search).get('theme') || 'pro').toLowerCase();
  if (t !== 'pro') return;
  var root = document.documentElement;
  root.classList.add('themed', 'theme-pro');
  var head = document.head || document.getElementsByTagName('head')[0];
  var fonts = document.createElement('link'); fonts.rel = 'stylesheet'; fonts.href = 'static/fonts/fonts.css';
  var css = document.createElement('link'); css.rel = 'stylesheet'; css.id = 'themeCss'; css.href = 'static/theme-pro.css';
  head.appendChild(fonts); head.appendChild(css);
  // feature scripts append their own stylesheets later (wow.css, audit.css, race.css): keep the theme last
  new MutationObserver(function () { if (head.lastElementChild !== css) head.appendChild(css); })
    .observe(head, { childList: true });

  // ---- labels: drop pictogram prefixes ("▶ Tour" -> "Tour"); the words stay identical
  var GLYPH = /^[\s←-⯿⌀-⏿■-◿☀-➿️€]*(?:\uD83C[\uDC00-\uDFFF]|\uD83D[\uDC00-\uDFFF]|\uD83E[\uDD00-\uDFFF])?[️‍\s]*/;
  function clean(btn) {
    for (var n = btn.firstChild; n; n = n.nextSibling) {
      if (n.nodeType === 3 && n.nodeValue.trim()) {
        var v = n.nodeValue.replace(GLYPH, ''); if (v.trim() && v !== n.nodeValue) n.nodeValue = v; break;
      }
      if (n.nodeType === 1 && !/^(B|SPAN|I|KBD)$/.test(n.tagName)) break;
    }
  }
  var SVG = {
    theme: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M8 2.5a5.5 5.5 0 0 1 0 11z" fill="currentColor"/></svg>',
    fit: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 6V2.5H6M10 2.5h3.5V6M13.5 10v3.5H10M6 13.5H2.5V10" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    chev: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 6.5 8 10l3.5-3.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    prev: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3.5 5.5 8l4.5 4.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    next: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3.5 10.5 8 6 12.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    search: '<svg class="qi" viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="4.75" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="m10.5 10.5 3 3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
    logo: '<svg class="logo" viewBox="0 0 24 24" aria-hidden="true"><rect x="1" y="1" width="22" height="22" rx="6" fill="currentColor"/><circle cx="12" cy="12" r="5.25" fill="none" stroke="#fff" stroke-width="1.6"/><circle cx="12" cy="12" r="1.6" fill="#fff"/></svg>'
  };
  function icon(sel, key) { var b = document.querySelector(sel); if (b && !b.dataset.pi) { b.dataset.pi = '1'; b.innerHTML = SVG[key]; } }

  // ---- Tools menu: Walk in 3D, BoQ, Identify, Audit, Scores, Cost race (same buttons, same ids, same handlers)
  var ITEMS = [
    { id: 'wowWalk', d: 'Extrude the plan and walk through it', k: 'W', g: 0 },
    { id: 'wowBoq', d: 'Quantity takeoff for this drawing', k: 'Q', g: 0 },
    { id: 'idBtn', d: 'Click any element to inspect it', k: 'I', g: 0 },
    { id: 'auBtn', d: 'Where the drawing disagrees with itself', k: 'A', g: 1 },
    { id: 'sbBtn', d: 'Every dataset question, auto-graded', k: '', g: 1 },
    { id: 'proRace', d: 'Measured cost vs a frontier VLM', k: 'R', g: 1 }
  ];
  var tools, pop, groups = [];
  function buildMenu() {
    if (tools) return true;
    var top = document.querySelector('.top'), tour = document.getElementById('tourBtn');
    if (!top || !tour) return false;
    tools = document.createElement('div'); tools.className = 'proTools'; tools.id = 'proTools';
    tools.innerHTML = '<button type="button" id="proToolsBtn" aria-haspopup="menu" aria-expanded="false">Tools' + SVG.chev + '<i class="proDot" hidden></i></button>'
      + '<div class="proPop" id="proPop" role="menu" hidden><div class="proG"><h6>Explore</h6></div><div class="proG"><h6>Verify</h6></div></div>';
    tour.after(tools);
    pop = tools.querySelector('#proPop'); groups = pop.querySelectorAll('.proG');
    var race = document.createElement('button'); race.type = 'button'; race.id = 'proRace'; race.textContent = 'Cost race';
    race.title = 'Cost race: measured cost per question vs a frontier vision model (R)';
    race.onclick = function () { var m = document.getElementById('meter'); if (m) m.click(); };
    pop.appendChild(race);
    var btn = tools.querySelector('#proToolsBtn');
    function open(on) {
      pop.hidden = !on; btn.setAttribute('aria-expanded', on ? 'true' : 'false'); tools.classList.toggle('open', on);
      if (on) { var f = pop.querySelector('button:not([disabled]):not([hidden])'); if (f) f.focus({ preventScroll: true }); }
    }
    btn.addEventListener('click', function (e) { e.stopPropagation(); open(pop.hidden); });
    document.addEventListener('click', function (e) { if (!pop.hidden && !tools.contains(e.target)) open(false); });
    pop.addEventListener('click', function (e) { if (e.target.closest('button')) setTimeout(function () { open(false); }, 0); });
    document.addEventListener('keydown', function (e) {
      if (pop.hidden) return;
      if (e.key === 'Escape') { open(false); btn.focus(); e.stopPropagation(); return; }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        var list = [].slice.call(pop.querySelectorAll('.proG button:not([disabled]):not([hidden])'));
        var i = list.indexOf(document.activeElement); i = (i + (e.key === 'ArrowDown' ? 1 : -1) + list.length) % list.length;
        list[i].focus(); e.preventDefault(); e.stopPropagation();
      }
    }, true);
    return true;
  }
  function adopt() {
    if (!buildMenu()) return;
    ITEMS.forEach(function (it) {
      var b = document.getElementById(it.id); if (!b || b.dataset.pm) return;
      b.dataset.pm = '1'; b.setAttribute('role', 'menuitem'); clean(b);
      var label = document.createElement('span'); label.className = 'proL';
      // move the visible label (text + badge) into one wrapper, then add a description and the shortcut
      while (b.firstChild) label.appendChild(b.firstChild);
      b.appendChild(label);
      var d = document.createElement('small'); d.className = 'proD'; d.textContent = it.d; label.appendChild(d);
      if (it.k) { var k = document.createElement('kbd'); k.textContent = it.k; b.appendChild(k); }
      groups[it.g].appendChild(b);
    });
    // keep menu order stable regardless of mount order
    ITEMS.forEach(function (it) { var b = document.getElementById(it.id); if (b && b.dataset.pm) groups[it.g].appendChild(b); });
    var au = document.querySelector('#auBtn .au-badge'), dot = tools.querySelector('.proDot');
    if (dot) dot.hidden = !(au && !au.hidden && au.textContent.trim());
  }
  function sweep() {
    document.querySelectorAll('.top .tbtn, .splash .cta button, #auditBtn, .wkAuto, #allBtn').forEach(clean);
    icon('#tglTheme', 'theme'); icon('#fitBtn', 'fit'); icon('#prevBtn', 'prev'); icon('#nextBtn', 'next');
    var qi = document.querySelector('.ask > svg.qi'); if (qi && !qi.dataset.pi) { var w = document.createElement('div'); w.innerHTML = SVG.search; var n = w.firstChild; n.dataset.pi = '1'; qi.replaceWith(n); }
    var lg = document.querySelector('.brand svg.logo'); if (lg && !lg.dataset.pi) { var w2 = document.createElement('div'); w2.innerHTML = SVG.logo; var n2 = w2.firstChild; n2.dataset.pi = '1'; lg.replaceWith(n2); }
    var go = document.querySelector('#go kbd'); if (go) go.hidden = true;
    adopt();
  }
  function boot() {
    sweep();
    var tb = document.getElementById('tourBtn');   // the tour rewrites its label ("▶ Tour" / "■ Stop")
    if (tb) new MutationObserver(function () { clean(tb); }).observe(tb, { childList: true, characterData: true, subtree: true });
    var k = 0, iv = setInterval(function () { sweep(); if (++k > 60) clearInterval(iv); }, 250);
    // overlays built later (BoQ, walk): same label clean-up, throttled to one pass per frame
    var DYN = '.bqTools button, .bqAct a, .bqAct button, .wkTgl, .wkSeg button, .wkAuto, .wkNav button, .idAct button', queued = false;
    new MutationObserver(function () {
      if (queued) return; queued = true;
      requestAnimationFrame(function () { queued = false; document.querySelectorAll(DYN).forEach(clean); });
    }).observe(document.body, { childList: true, subtree: true });
    setInterval(function () { var au = document.querySelector('#auBtn .au-badge'), dot = document.querySelector('#proTools .proDot'); if (dot) dot.hidden = !(au && !au.hidden && au.textContent.trim()); }, 1000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
