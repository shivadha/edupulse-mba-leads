/* EduPulse — Landing page JS (vanilla, no dependencies) */
'use strict';

/* ── UTM capture → hidden field (POST /submit-lead contract) ── */
(function captureUtm() {
  try {
    const q = new URLSearchParams(window.location.search);
    const utm = q.get('utm_source') || q.get('utm') || document.referrer || 'landing';
    const el = document.getElementById('lf-utm');
    if (el) el.value = utm.slice(0, 120);
  } catch (e) { /* non-fatal */ }
})();

/* ── Animated counters ───────────────────────────────────── */
function animateCount(el) {
  const target = parseInt(el.dataset.count, 10) || 0;
  const dur = 1400, t0 = performance.now();
  function tick(t) {
    const p = Math.min((t - t0) / dur, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(target * eased).toLocaleString('en-IN');
    if (p < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

/* Fetch a real signal count for the stats strip, when available */
function hydrateLiveCount() {
  fetch('/api/intelligence?limit=500')
    .then(r => (r.ok ? r.json() : Promise.reject()))
    .then(items => {
      const el = document.querySelector('.hero-stats [data-count="13"]');
      if (el && items.length) {
        el.dataset.count = String(Math.min(items.length, 999));
        animateCount(el);
      }
    })
    .catch(() => {});
}

/* ── College marquee ─────────────────────────────────────── */
function buildMarquee() {
  const track = document.getElementById('collegeTrack');
  if (!track) return;
  const colleges = [
    'IIM Ahmedabad', 'IIM Bangalore', 'IIM Calcutta', 'XLRI Jamshedpur',
    'FMS Delhi', 'SPJIMR Mumbai', 'MDI Gurgaon', 'IIFT Delhi',
    'IIM Lucknow', 'IIM Kozhikode', 'NMIMS Mumbai', 'SIBM Pune',
    'JBIMS Mumbai', 'TISS Mumbai', 'IIM Indore', 'IIM Shillong',
  ];
  const seq = colleges.map(c => '<span>' + c + '</span>').join('');
  track.innerHTML = seq + seq; // duplicate for seamless loop
}

/* ── FAQ accordion ───────────────────────────────────────── */
function toggleFaq(btn) {
  const item = btn.closest('.faq');
  const answer = item.querySelector('.faq-a');
  const wasOpen = item.classList.contains('open');
  document.querySelectorAll('.faq.open').forEach(f => {
    f.classList.remove('open');
    f.querySelector('.faq-a').style.maxHeight = null;
  });
  if (!wasOpen) {
    item.classList.add('open');
    answer.style.maxHeight = answer.scrollHeight + 'px';
  }
}

/* ── Lead form ───────────────────────────────────────────── */
function setFormError(msg) {
  const box = document.getElementById('formError');
  if (!box) return;
  box.textContent = msg || '';
  box.classList.toggle('show', !!msg);
}

function validPhone(p) {
  return /^[6-9]\d{9}$/.test(p.replace(/\s+/g, ''));
}

function submitCounsellingForm(event) {
  event.preventDefault();
  setFormError('');

  const name = document.getElementById('lf-name').value.trim();
  const phone = document.getElementById('lf-phone').value.trim();
  const city = document.getElementById('lf-city').value.trim();
  const email = document.getElementById('lf-email').value.trim();

  if (name.length < 2) { setFormError('Please enter your full name.'); return false; }
  if (!validPhone(phone)) { setFormError('Please enter a valid 10-digit mobile number.'); return false; }
  if (city.length < 2) { setFormError('Please enter your city.'); return false; }

  const btn = document.getElementById('fSubmit');
  const original = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = 'Submitting…';

  const payload = new URLSearchParams();
  payload.set('name', name);
  payload.set('phone', phone);
  payload.set('email', email);
  payload.set('city', city);
  payload.set('target_exam', document.getElementById('lf-exam').value);
  payload.set('target_year', document.getElementById('lf-year').value);
  payload.set('utm_source', document.getElementById('lf-utm').value || 'landing');

  fetch('/submit-lead', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: payload.toString(),
  })
    .then(res => {
      if (!res.ok) throw new Error('Server returned ' + res.status);
      window.location.href = '/thank-you?name=' + encodeURIComponent(name.split(' ')[0]);
    })
    .catch(err => {
      btn.disabled = false;
      btn.innerHTML = original;
      setFormError('Something went wrong. Please try again, or refresh the page.');
      console.error('Lead submit failed:', err);
    });
  return false;
}

/* ── Sticky CTA visibility ───────────────────────────────── */
function watchStickyCta() {
  const cta = document.getElementById('stickyCta');
  const form = document.getElementById('lead-form');
  if (!cta || !form || !('IntersectionObserver' in window)) return;
  const io = new IntersectionObserver(entries => {
    entries.forEach(e => cta.classList.toggle('show', !e.isIntersecting && e.boundingClientRect.top > 0));
  }, { threshold: 0 });
  io.observe(form);
}

/* ── Boot ────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  buildMarquee();
  watchStickyCta();
  document.querySelectorAll('.hero-stats .num[data-count]').forEach(animateCount);
  hydrateLiveCount();
});
