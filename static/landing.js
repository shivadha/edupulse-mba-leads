// EduPulse India — Landing Page JS

// ── Year button selector ──────────────────────────────────────────
document.querySelectorAll('.year-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.year-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('target_year').value = btn.dataset.year;
  });
});

// ── Live stats counter ────────────────────────────────────────────
async function loadStats() {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();
    animateCounter('stat-leads', data.total || 0);
    const intel = await fetch('/api/intelligence?limit=1');
    // Just show total rows via count
    const leadsData = await fetch('/api/leads?limit=1');
  } catch {}
}

function animateCounter(id, target) {
  const el = document.getElementById(id);
  if (!el) return;
  let start = 0;
  const duration = 1500;
  const step = target / (duration / 16);
  const timer = setInterval(() => {
    start += step;
    if (start >= target) { start = target; clearInterval(timer); }
    el.textContent = Math.floor(start).toLocaleString('en-IN');
  }, 16);
}

// Set sample intel count (will update when scraped data comes in)
function setIntelCount() {
  fetch('/api/intelligence?limit=500')
    .then(r => r.json())
    .then(d => animateCounter('stat-intel', d.length))
    .catch(() => {});
}

window.addEventListener('DOMContentLoaded', () => {
  loadStats();
  setIntelCount();
});

// ── Form submission (AJAX) ────────────────────────────────────────
const form = document.getElementById('leadForm');
const btn = document.getElementById('submitBtn');

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const btnText = btn.querySelector('.btn-text');
  const btnLoader = btn.querySelector('.btn-loader');
  btn.disabled = true;
  btnText.hidden = true;
  btnLoader.hidden = false;

  const formData = new FormData(form);

  try {
    const res = await fetch('/submit-lead', {
      method: 'POST',
      body: formData,
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    const data = await res.json();

    if (data.ok) {
      showToast('🎉 Registered successfully! We\'ll contact you soon.');
      form.reset();
      // Reset year buttons
      document.querySelectorAll('.year-btn').forEach(b => b.classList.remove('active'));
      document.querySelector('.year-btn[data-year="2025"]').classList.add('active');
      document.getElementById('target_year').value = '2025';
      // Animate the lead counter up by 1
      const el = document.getElementById('stat-leads');
      if (el) {
        const current = parseInt(el.textContent.replace(/,/g, '')) || 0;
        animateCounter('stat-leads', current + 1);
      }
    } else {
      showToast('⚠️ ' + (data.error || 'Something went wrong. Please try again.'), 'error');
    }
  } catch (err) {
    showToast('⚠️ Network error. Please try again.', 'error');
  }

  btn.disabled = false;
  btnText.hidden = false;
  btnLoader.hidden = true;
});

// ── Toast ─────────────────────────────────────────────────────────
function showToast(msg, type = 'success') {
  const toast = document.getElementById('toast');
  const msgEl = document.getElementById('toastMsg');
  const iconEl = toast.querySelector('.toast-icon');
  msgEl.textContent = msg;
  if (type === 'error') {
    toast.style.background = '#2f1a1a';
    toast.style.borderColor = '#5a2d2d';
    iconEl.textContent = '⚠️';
  } else {
    toast.style.background = '#1a2f1a';
    toast.style.borderColor = '#2d5a2d';
    iconEl.textContent = '✅';
  }
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 4000);
}
