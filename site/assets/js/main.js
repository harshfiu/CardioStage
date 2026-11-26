/*
 * CardioStage landing site.
 *
 * 1. Fill every number from window.CARDIOSTAGE_DATA (generated from the
 *    project's real results by `python -m cardiostage.site_data`).
 * 2. Build the charts with DOM APIs (no HTML strings, which keeps us inside
 *    the page's strict Content-Security-Policy).
 * 3. Add motion with Lenis, GSAP and Vanta, but only if the visitor hasn't
 *    asked for reduced motion and the libraries loaded. Without motion,
 *    everything is shown in its final state.
 */
(function () {
  "use strict";

  var D = window.CARDIOSTAGE_DATA;
  var REDUCE = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var HAS_GSAP = !!(window.gsap && window.ScrollTrigger);
  var MOTION = !REDUCE && HAS_GSAP;

  // ---------- helpers ----------
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function pct(x, digits) { return (x * 100).toFixed(digits || 0) + "%"; }
  function setText(sel, value) {
    document.querySelectorAll(sel).forEach(function (n) { n.textContent = value; });
  }

  // ---------- 1. numbers ----------
  function fillNumbers() {
    if (!D) return;
    var cv = D.strategies.cv, test = D.strategies.sealed_test;
    var inv = cv.invasive_difference;
    var counts = {
      invasive_reduction: Math.round(-inv.value * 100),
      sealed_missed: test.sick_missed,
    };
    // Small number: shown directly (a 0→3 count-up reads "1 hospitals" mid-way).
    setText('[data-bind="hospitals"]', String(D.v2 ? D.v2.hospitals.length : 5));
    if (D.v2) {
      var v2all = function (v) { return D.v2.sealed_test_second_look.filter(function (r) { return r.hospital === "All hospitals" && r.version === v; })[0]; };
      setText('[data-bind="v1_auc"]', v2all("v1").auc.value.toFixed(2));
      setText('[data-bind="v2_auc"]', v2all("v2").auc.value.toFixed(2));
      setText('[data-bind="v1_cleared"]', String(v2all("v1").cleared_but_sick));
      setText('[data-bind="v2_cleared"]', String(v2all("v2").cleared_but_sick));
      var ta = D.v2.typical_angina_iran;
      setText('[data-bind="ta_actual"]', pct(ta.actual)); setText('[data-bind="ta_v1"]', pct(ta.v1)); setText('[data-bind="ta_v2"]', pct(ta.v2));
      var first = D.v2.first_look_all.filter(function (r) { return r.version === "v2"; })[0];
      setText('[data-bind="first_auc"]', first.auc.value.toFixed(2));
      setText('[data-bind="first_cleared"]', String(first.cleared_but_sick));
    }
    if (D.chatbots) {
      var bot = function (s) { return D.chatbots.rows.filter(function (r) { return r.group === "All hospitals" && r.source === s; })[0]; };
      var cs = bot("CardioStage v2"), cl = bot("claude"), gp = bot("chatgpt");
      setText('[data-bind="bot_cs_auc"]', cs.auc.value.toFixed(2));
      setText('[data-bind="bot_claude_auc"]', cl.auc.value.toFixed(2));
      setText('[data-bind="bot_gpt_auc"]', gp.auc.value.toFixed(2));
      setText('[data-bind="bot_pred"]', pct((cl.mean_predicted + gp.mean_predicted) / 2));
      setText('[data-bind="bot_actual"]', pct(cs.disease_rate));
      setText('[data-bind="bot_cs_ece"]', cs.ece.toFixed(3));
      setText('[data-bind="bot_llm_ece"]', ((cl.ece + gp.ece) / 2).toFixed(2));
      setText('[data-bind="bot_cs_cleared"]', pct(cs.share_cleared));
      setText('[data-bind="bot_claude_missed"]', String(cl.cleared_but_sick));
      setText('[data-bind="bot_gpt_missed"]', String(gp.cleared_but_sick));
    }
    document.querySelectorAll("[data-count]").forEach(function (n) {
      var v = counts[n.dataset.count];
      n.dataset.target = v;
      n.textContent = v + (n.dataset.suffix || "");
    });
    setText('[data-bind="invasive_ci"]', Math.round(-inv.high * 100) + "–" + Math.round(-inv.low * 100) + "%");
    setText('[data-bind="sealed_recall_ci"]', pct(test.recall.low, 1) + "–" + pct(test.recall.high));
    setText('[data-bind="target_recall"]', pct(D.targets.screening_recall));
    setText('[data-bind="cv_patients"]', cv.n_patients);
    setText('[data-bind="example_risk"]', pct(D.example.risk));
    setText('[data-bind="example_base"]', pct(D.example.baseline));
    setText('[data-bind="sealed_sick"]', String(test.n_sick));

    // Stage flow sentences.
    D.flow.forEach(function (f) {
      var node = document.querySelector('[data-flow="' + f.stage + '"]');
      if (!node) return;
      var parts = ["Of " + f.reached + " people: " + f.cleared + " reassured", f.referred + " referred"];
      if (f.onward) parts.push(f.onward + " go on to " + (f.stage === 1 ? "the treadmill test" : "imaging"));
      node.textContent = parts.join(", ") + ".";
    });
  }
  // ---------- 2. charts ----------
  function chartCompare() {
    var host = document.querySelector('[data-chart="compare"]');
    if (!host || !D) return;
    var cv = D.strategies.cv;
    [
      { label: "Everyone gets every test", v: cv.all_tests.needed_invasive, brand: false },
      { label: "CardioStage, step by step", v: cv.staged.needed_invasive, brand: true },
    ].forEach(function (r) {
      var row = el("div", "bar__row");
      var head = el("div", "bar__head");
      head.appendChild(el("span", "", r.label));
      head.appendChild(el("span", "bar__value" + (r.brand ? " bar__value--warm" : ""), pct(r.v)));
      var track = el("div", "bar__track");
      var fill = el("div", "bar__fill" + (r.brand ? " bar__fill--brand" : ""));
      fill.style.width = pct(r.v, 1);
      track.appendChild(fill);
      row.appendChild(head); row.appendChild(track);
      host.appendChild(row);
    });
    var foot = document.querySelector('[data-bind="compare_foot"]');
    if (foot) {
      foot.textContent = "";
      foot.appendChild(document.createTextNode("Sick patients missed: "));
      foot.appendChild(el("strong", "", String(cv.all_tests.sick_missed)));
      foot.appendChild(document.createTextNode(" vs "));
      foot.appendChild(el("strong", "", String(cv.staged.sick_missed)));
      foot.appendChild(document.createTextNode(" of " + cv.staged.n_sick + " · Recall "));
      foot.appendChild(el("strong", "", pct(cv.all_tests.recall, 1)));
      foot.appendChild(document.createTextNode(" vs "));
      foot.appendChild(el("strong", "", pct(cv.staged.recall, 1)));
    }
  }

  function chartFlow() {
    var host = document.querySelector('[data-chart="flow"]');
    if (!host || !D) return;
    var total = D.flow[0].reached;
    D.flow.forEach(function (f) {
      var row = el("div", "flow__row");
      var label = el("div", "flow__label");
      label.appendChild(el("strong", "", "Stage " + f.stage + ": " + f.name.replace(/^\+ /, "")));
      label.appendChild(document.createTextNode(f.reached + " people reached this stage"));
      var bar = el("div", "flow__bar");
      bar.setAttribute("role", "img");
      bar.setAttribute("aria-label", "Stage " + f.stage + ": " + f.cleared + " reassured, " + f.referred + " referred, " + f.onward + " sent to the next test");
      [["clear", f.cleared], ["refer", f.referred], ["next", f.onward]].forEach(function (s) {
        if (!s[1]) return;
        var seg = el("span", "flow__seg flow__seg--" + s[0], s[1] >= 12 ? String(s[1]) : "");
        seg.style.width = (s[1] / total * 100).toFixed(2) + "%";
        bar.appendChild(seg);
      });
      row.appendChild(label); row.appendChild(bar);
      host.appendChild(row);
    });
  }

  function chartExplain() {
    var host = document.querySelector('[data-chart="explain"]');
    if (!host || !D) return;
    var items = D.example.contributions.slice(0, 6);
    var max = Math.max.apply(null, items.map(function (c) { return Math.abs(c.points); }));
    items.forEach(function (c) {
      var label = el("div", "explain__label");
      label.appendChild(document.createTextNode(c.label + " "));
      label.appendChild(el("span", "", "= " + c.value.replace(/ \(.*\)$/, "")));
      var track = el("div", "explain__track");
      track.appendChild(el("span", "explain__axis"));
      var up = c.points >= 0;
      var w = Math.max(Math.abs(c.points) / max * 46, 0.6);
      var bar = el("span", "explain__bar " + (up ? "explain__bar--up" : "explain__bar--down"));
      bar.style.width = w + "%";
      var num = el("span", "explain__num", (up ? "+" : "−") + Math.abs(c.points).toFixed(1));
      num.setAttribute("aria-hidden", "true");
      track.setAttribute("role", "img");
      track.setAttribute("aria-label", c.label + ": " + (up ? "raises" : "lowers") + " risk by " + Math.abs(c.points).toFixed(1) + " points");
      track.appendChild(bar);
      host.appendChild(label); host.appendChild(track); host.appendChild(num);
    });
  }

  function chartHospitals() {
    var host = document.querySelector('[data-chart="hospitals"]');
    if (!host || !D) return;
    var lo = 0.4, hi = 1.0;
    function x(v) { return ((v - lo) / (hi - lo) * 100).toFixed(2) + "%"; }
    D.external.forEach(function (h) {
      var row = el("div", "hosp__row");
      var name = el("div", "hosp__name", h.internal ? "Cleveland" : h.hospital);
      name.appendChild(el("span", "", (h.internal ? "home hospital, unseen patients · " : "") + "n=" + h.n + ", " + pct(h.disease_rate) + " with disease"));
      var plot = el("div", "hosp__plot");
      plot.setAttribute("role", "img");
      plot.setAttribute("aria-label", name.firstChild.textContent + ": check-up stage AUC " + h.stage1.value.toFixed(2) + " (" + h.stage1.low.toFixed(2) + " to " + h.stage1.high.toFixed(2) + "), treadmill stage AUC " + h.stage2.value.toFixed(2) + " (" + h.stage2.low.toFixed(2) + " to " + h.stage2.high.toFixed(2) + ")");
      [0.5, 0.6, 0.7, 0.8, 0.9].forEach(function (g) { var gl = el("span", "hosp__grid"); gl.style.left = x(g); plot.appendChild(gl); });
      [["s1", h.stage1], ["s2", h.stage2]].forEach(function (s) {
        var ci = el("span", "hosp__ci hosp__ci--" + s[0]);
        ci.style.left = x(s[1].low); ci.style.width = "calc(" + x(s[1].high) + " - " + x(s[1].low) + ")";
        var pt = el("span", "hosp__pt hosp__pt--" + s[0]);
        pt.style.left = x(s[1].value);
        plot.appendChild(ci); plot.appendChild(pt);
      });
      row.appendChild(name); row.appendChild(plot);
      host.appendChild(row);
    });
    var axis = el("div", "hosp__axis");
    axis.appendChild(el("span", "", "ROC-AUC"));
    var ticks = el("div", "hosp__ticks");
    [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0].forEach(function (t) { var s = el("span", "", t.toFixed(1)); s.style.left = x(t); ticks.appendChild(s); });
    axis.appendChild(ticks);
    host.appendChild(axis);
  }

  function chartV2() {
    var host = document.querySelector('[data-chart="v2"]');
    if (!host || !D || !D.v2) return;
    var lo = 0.4, hi = 1.0;
    function x(v) { return ((Math.max(lo, v) - lo) / (hi - lo) * 100).toFixed(2) + "%"; }
    var rows = D.v2.sealed_test_second_look;
    D.v2.hospitals.concat(["All hospitals"]).forEach(function (hname) {
      var get = function (v) { return rows.filter(function (r) { return r.hospital === hname && r.version === v; })[0]; };
      var a = get("v1"), b = get("v2");
      if (!a || !b || !a.auc || !b.auc) return;
      var row = el("div", "hosp__row");
      var name = el("div", "hosp__name", hname);
      name.appendChild(el("span", "", "n=" + b.n + " sealed-test patients"));
      var plot = el("div", "hosp__plot");
      plot.setAttribute("role", "img");
      plot.setAttribute("aria-label", hname + ": version 2 AUC " + b.auc.value.toFixed(2) + " (" + b.auc.low.toFixed(2) + " to " + b.auc.high.toFixed(2) + "), version 1 AUC " + a.auc.value.toFixed(2) + " (" + a.auc.low.toFixed(2) + " to " + a.auc.high.toFixed(2) + ")");
      [0.5, 0.6, 0.7, 0.8, 0.9].forEach(function (g) { var gl = el("span", "hosp__grid"); gl.style.left = x(g); plot.appendChild(gl); });
      [["s1", b.auc], ["s2", a.auc]].forEach(function (s) {
        var ci = el("span", "hosp__ci hosp__ci--" + s[0]);
        ci.style.left = x(s[1].low); ci.style.width = "calc(" + x(s[1].high) + " - " + x(s[1].low) + ")";
        var pt = el("span", "hosp__pt hosp__pt--" + s[0]);
        pt.style.left = x(s[1].value);
        plot.appendChild(ci); plot.appendChild(pt);
      });
      row.appendChild(name); row.appendChild(plot);
      host.appendChild(row);
    });
    var axis = el("div", "hosp__axis");
    axis.appendChild(el("span", "", "ROC-AUC"));
    var ticks = el("div", "hosp__ticks");
    [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0].forEach(function (t) { var s = el("span", "", t.toFixed(1)); s.style.left = x(t); ticks.appendChild(s); });
    axis.appendChild(ticks);
    host.appendChild(axis);
  }

  function chartBots() {
    var host = document.querySelector('[data-chart="chatbots"]');
    if (!host || !D || !D.chatbots) return;
    var lo = 0.4, hi = 1.0;
    function x(v) { return ((Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo) * 100).toFixed(2) + "%"; }
    var C = D.chatbots;
    var order = [["s1", "CardioStage v2"], ["s2", "claude"], ["s3", "chatgpt"]];
    C.groups.forEach(function (g) {
      var get = function (s) { return C.rows.filter(function (r) { return r.group === g && r.source === s; })[0]; };
      var rows = order.map(function (o) { return get(o[1]); });
      if (rows.some(function (r) { return !r || !r.auc; })) return;
      var row = el("div", "hosp__row");
      var name = el("div", "hosp__name", g);
      name.appendChild(el("span", "", "n=" + rows[0].n + " sealed-test patients"));
      var plot = el("div", "hosp__plot");
      plot.setAttribute("role", "img");
      plot.setAttribute("aria-label", g + ": " + order.map(function (o, i) {
        var a = rows[i].auc; return C.sources[o[1]] + " AUC " + a.value.toFixed(2) + " (" + a.low.toFixed(2) + " to " + a.high.toFixed(2) + ")";
      }).join(", "));
      [0.5, 0.6, 0.7, 0.8, 0.9].forEach(function (v) { var gl = el("span", "hosp__grid"); gl.style.left = x(v); plot.appendChild(gl); });
      order.forEach(function (o, i) {
        var a = rows[i].auc;
        var ci = el("span", "hosp__ci hosp__ci--" + o[0]);
        ci.style.left = x(a.low); ci.style.width = "calc(" + x(a.high) + " - " + x(a.low) + ")";
        var pt = el("span", "hosp__pt hosp__pt--" + o[0]);
        pt.style.left = x(a.value);
        plot.appendChild(ci); plot.appendChild(pt);
      });
      row.appendChild(name); row.appendChild(plot);
      host.appendChild(row);
    });
    var axis = el("div", "hosp__axis");
    axis.appendChild(el("span", "", "ROC-AUC (intervals below 0.4 are cut off)"));
    var ticks = el("div", "hosp__ticks");
    [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0].forEach(function (t) { var s = el("span", "", t.toFixed(1)); s.style.left = x(t); ticks.appendChild(s); });
    axis.appendChild(ticks);
    host.appendChild(axis);
  }

  // Show the "open local app" button only when viewing the site on this computer.
  function localAppLink() {
    var local = location.protocol === "file:" || location.hostname === "localhost" || location.hostname === "127.0.0.1";
    var a = document.getElementById("local-app");
    if (a && local) a.classList.remove("is-hidden");
  }

  // ---------- 3. motion ----------
  function initMotion() {
    var gsap = window.gsap, ST = window.ScrollTrigger;
    var plugins = [ST];
    if (window.DrawSVGPlugin) plugins.push(window.DrawSVGPlugin);
    if (window.SplitText) plugins.push(window.SplitText);
    gsap.registerPlugin.apply(gsap, plugins);

    // Lenis smooth scrolling, driven by GSAP's ticker so ScrollTrigger stays in sync.
    if (window.Lenis) {
      var lenis = new window.Lenis({ lerp: 0.1, smoothWheel: true });
      lenis.on("scroll", ST.update);
      gsap.ticker.add(function (t) { lenis.raf(t * 1000); });
      gsap.ticker.lagSmoothing(0);
      document.querySelectorAll('a[href^="#"]').forEach(function (a) {
        a.addEventListener("click", function (e) {
          var id = a.getAttribute("href");
          if (id.length < 2) return;
          var target = document.querySelector(id);
          if (!target) return;
          e.preventDefault();
          lenis.scrollTo(target, { offset: -72 });
          target.setAttribute("tabindex", "-1");
          target.focus({ preventScroll: true });
        });
      });
    }

    // Hero: words rise in, then the line art and ECG draw themselves.
    var title = document.getElementById("hero-title");
    if (window.SplitText && title) {
      var split = new window.SplitText(title, { type: "words", mask: "words", aria: "auto" });
      gsap.from(split.words, { yPercent: 110, opacity: 0, duration: 0.9, ease: "power3.out", stagger: 0.045 });
    }
    gsap.from(".hero .lead, .hero .actions, .hero .eyebrow", { y: 18, opacity: 0, duration: 0.8, delay: 0.35, stagger: 0.1, ease: "power2.out" });
    if (window.DrawSVGPlugin) {
      gsap.from(".hero__art path", { drawSVG: "0%", duration: 1.8, delay: 0.3, ease: "power2.inOut", stagger: 0.25 });
      gsap.from(".hero__ecg path", { drawSVG: "0%", duration: 2.4, delay: 0.6, ease: "power1.inOut" });
      // Other illustrations draw as they scroll into view.
      gsap.utils.toArray("svg.draw").forEach(function (svg) {
        if (svg.closest(".hero")) return;
        gsap.from(svg.querySelectorAll("path, circle"), { drawSVG: "0%", duration: 1.4, ease: "power2.inOut", stagger: 0.15,
          scrollTrigger: { trigger: svg, start: "top 85%", once: true } });
      });
    }

    // Gentle reveals.
    gsap.utils.toArray(".reveal").forEach(function (n) {
      gsap.from(n, { y: 28, opacity: 0, duration: 0.8, ease: "power2.out", scrollTrigger: { trigger: n, start: "top 88%", once: true } });
    });

    // Count-up numbers.
    document.querySelectorAll("[data-count]").forEach(function (n) {
      var target = Number(n.dataset.target || n.textContent.replace(/\D/g, ""));
      var obj = { v: 0 }, suffix = n.dataset.suffix || "";
      n.textContent = "0" + suffix;
      gsap.to(obj, { v: target, duration: 1.4, ease: "power2.out", scrollTrigger: { trigger: n, start: "top 90%", once: true },
        onUpdate: function () { n.textContent = Math.round(obj.v) + suffix; } });
    });

    // Bars grow from zero.
    gsap.from(".bar__fill", { scaleX: 0, duration: 1.2, ease: "power3.out", stagger: 0.2, scrollTrigger: { trigger: "#chart-compare", start: "top 80%", once: true } });
    gsap.from(".flow__seg", { scaleX: 0, duration: 0.8, ease: "power2.out", stagger: 0.08, scrollTrigger: { trigger: "#chart-flow", start: "top 80%", once: true } });
    gsap.from(".explain__bar", { scaleX: 0, duration: 0.9, ease: "power2.out", stagger: 0.08, scrollTrigger: { trigger: ".explain", start: "top 85%", once: true } });
    gsap.utils.toArray(".hosp").forEach(function (hc) { gsap.from(hc.querySelectorAll(".hosp__pt, .hosp__ci"), { opacity: 0, duration: 0.6, stagger: 0.04, scrollTrigger: { trigger: hc, start: "top 85%", once: true } }); });

    // "How it works": pinned on wide screens; stages light up in turn while a dot travels.
    var mm = gsap.matchMedia();
    var stages = gsap.utils.toArray(".stage");
    mm.add("(min-width: 900px)", function () {
      var tl = gsap.timeline({ scrollTrigger: { trigger: ".how", start: "top top", end: "+=1400", scrub: 0.6, pin: true } });
      stages.forEach(function (s, i) {
        tl.to(".how__line", { width: ((i + 1) / stages.length * 100) + "%", duration: 1, ease: "none" }, i)
          .to(".how__dot", { left: ((i + 1) / stages.length * 100) + "%", duration: 1, ease: "none" }, i)
          .call(function () { stages.forEach(function (o, j) { o.classList.toggle("is-active", j <= i); }); }, null, i + 0.5);
      });
    });
    mm.add("(max-width: 899px)", function () {
      stages.forEach(function (s) {
        ST.create({ trigger: s, start: "top 75%", onEnter: function () { s.classList.add("is-active"); } });
      });
    });
    stages[0] && stages[0].classList.add("is-active");

    initVanta();
  }

  // Vanta NET background: only while the hero is on screen (saves battery/GPU).
  function initVanta() {
    var host = document.getElementById("hero-bg");
    if (!host || !window.VANTA || !window.THREE) return;
    var effect = null;
    function start() {
      if (effect) return;
      try {
        effect = window.VANTA.NET({ el: host, THREE: window.THREE, mouseControls: true, touchControls: true, gyroControls: false,
          minHeight: 200, minWidth: 200, scale: 1, scaleMobile: 1,
          color: 0x5b8fe8, backgroundColor: 0x080b12, points: 9, maxDistance: 21, spacing: 18, showDots: true });
      } catch (e) { effect = null; }  // no WebGL: keep the static gradient
    }
    function stop() { if (effect) { effect.destroy(); effect = null; } }
    new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { en.isIntersecting ? start() : stop(); });
    }, { threshold: 0.05 }).observe(host);
  }

  // ---------- go ----------
  try { fillNumbers(); chartCompare(); chartFlow(); chartExplain(); chartHospitals(); chartV2(); chartBots(); } catch (e) { /* static fallbacks stay */ }
  localAppLink();
  if (MOTION) {
    document.documentElement.classList.add("has-motion");
    try { initMotion(); } catch (e) { /* content is already fully visible */ }
  } else {
    document.querySelectorAll(".stage").forEach(function (s) { s.classList.add("is-active"); });
  }
})();
