/* EduPulse CAT Predictor — vanilla JS, zero dependencies. */
(function () {
  "use strict";

  var els = {
    name: document.getElementById("inName"),
    phone: document.getElementById("inPhone"),
    category: document.getElementById("inCategory"),
    gender: document.getElementById("inGender"),
    pct: document.getElementById("inPct"),
    pctOut: document.getElementById("pctOut"),
    predictBtn: document.getElementById("predictBtn"),
    predError: document.getElementById("predError"),
    results: document.getElementById("results"),
    counts: document.getElementById("counts"),
    cards: document.getElementById("cards"),
    filters: document.getElementById("filters"),
    waBtn: document.getElementById("waBtn"),
    leadError: document.getElementById("leadError"),
    toast: document.getElementById("toast"),
  };

  var lastPredictions = [];
  var activeFilter = "all";
  var lastLeadKey = null; // prevents double-submits for the same inputs

  /* ── slider ── */
  function paintSlider() {
    var min = parseFloat(els.pct.min), max = parseFloat(els.pct.max);
    var v = parseFloat(els.pct.value);
    els.pctOut.textContent = v;
    els.pct.style.setProperty("--fill", ((v - min) / (max - min)) * 100 + "%");
  }
  els.pct.addEventListener("input", paintSlider);
  paintSlider();

  /* ── toast ── */
  var toastTimer = null;
  function toast(msg) {
    els.toast.textContent = msg;
    els.toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { els.toast.classList.remove("show"); }, 3500);
  }

  function err(el, msg) {
    el.textContent = msg || "";
  }

  /* ── predict ── */
  function doPredict() {
    err(els.predError);
    var pct = parseFloat(els.pct.value);
    if (!(pct > 0 && pct <= 100)) {
      err(els.predError, "Please choose a percentile between 60 and 100.");
      return;
    }
    els.predictBtn.disabled = true;
    els.predictBtn.textContent = "Checking…";

    fetch("/api/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cat_percentile: pct,
        category: els.category.value,
        gender: els.gender.value,
      }),
    })
      .then(function (res) { return res.json().then(function (d) { return { ok: res.ok, d: d }; }); })
      .then(function (r) {
        if (!r.ok) { err(els.predError, r.d.error || "Could not run the prediction. Try again."); return; }
        lastPredictions = r.d.predictions || [];
        renderResults(r.d.counts || { safe: 0, target: 0, reach: 0 });
      })
      .catch(function () { err(els.predError, "Network error. Check your connection and try again."); })
      .finally(function () {
        els.predictBtn.disabled = false;
        els.predictBtn.innerHTML = 'Check my college chances <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></svg>';
      });
  }
  els.predictBtn.addEventListener("click", doPredict);

  /* ── results ── */
  function tagWord(t) { return t.charAt(0).toUpperCase() + t.slice(1); }

  function renderResults(counts) {
    els.results.hidden = false;
    els.counts.innerHTML =
      '<span class="c-safe">● ' + counts.safe + ' safe</span>' +
      '<span class="c-target">● ' + counts.target + ' target</span>' +
      '<span class="c-reach">● ' + counts.reach + ' reach</span>';
    renderCards();
    els.results.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderCards() {
    var list = activeFilter === "all"
      ? lastPredictions
      : lastPredictions.filter(function (c) { return c.tag === activeFilter; });
    if (!list.length) {
      els.cards.innerHTML = '<p style="color:var(--muted)">No colleges in this bucket at your percentile. Try a different filter.</p>';
      return;
    }
    els.cards.innerHTML = list.map(function (c) {
      var meta = '<span>Cutoff <b>' + c.cutoff + '%ile</b></span>';
      if (c.avg_package_lpa) meta += '<span>Avg pkg <b>₹' + c.avg_package_lpa + ' LPA</b></span>';
      if (c.fees_lakhs) meta += '<span>Fees <b>₹' + c.fees_lakhs + 'L</b></span>';
      return (
        '<article class="p-college">' +
          '<div class="p-college-top"><h3>' + escapeHtml(c.name) + '</h3>' +
          '<span class="badge ' + c.tag + '">' + tagWord(c.tag) + '</span></div>' +
          '<div class="city">' + escapeHtml(c.city) + '</div>' +
          '<div class="p-meta">' + meta + '</div>' +
          '<div class="p-tier">' + escapeHtml(c.tier) + '</div>' +
        '</article>'
      );
    }).join("");
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  els.filters.addEventListener("click", function (e) {
    var btn = e.target.closest("button[data-f]");
    if (!btn) return;
    activeFilter = btn.getAttribute("data-f");
    Array.prototype.forEach.call(els.filters.querySelectorAll("button"), function (b) {
      b.classList.toggle("on", b === btn);
    });
    renderCards();
  });

  /* ── lead capture → WhatsApp CTA ── */
  els.waBtn.addEventListener("click", function () {
    err(els.leadError);
    var name = els.name.value.trim();
    var phone = els.phone.value.replace(/[\s\-+]/g, "");
    if (name.length < 2) { err(els.leadError, "Please enter your name above first."); els.name.focus(); return; }
    if (!/^[6-9]\d{9}$/.test(phone.replace(/^91(?=\d{10}$)/, ""))) {
      err(els.leadError, "Please enter a valid 10-digit mobile number above first."); els.phone.focus(); return;
    }
    var key = name + "|" + phone + "|" + els.pct.value + "|" + els.category.value;
    if (key === lastLeadKey) { toast("Already saved — check your WhatsApp soon!"); return; }

    els.waBtn.disabled = true;
    els.waBtn.textContent = "Saving…";

    fetch("/api/predict/lead", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: name,
        phone: phone,
        cat_percentile: parseFloat(els.pct.value),
        category: els.category.value,
      }),
    })
      .then(function (res) { return res.json().then(function (d) { return { ok: res.ok, d: d }; }); })
      .then(function (r) {
        if (!r.ok) { err(els.leadError, r.d.error || "Could not save. Try again."); return; }
        lastLeadKey = key;
        toast("Done! Your personalised list is on its way to WhatsApp.");
      })
      .catch(function () { err(els.leadError, "Network error. Try again."); })
      .finally(function () {
        els.waBtn.disabled = false;
        els.waBtn.innerHTML = 'Get my full list on WhatsApp';
      });
  });
})();
