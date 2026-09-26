/* EduPulse — Admissions Intelligence Console
   Vanilla JS. API contracts (do not change shapes):
   GET  /api/intelligence?source=&exam=&limit=
   GET  /api/stats   GET /api/leads?exam=&limit=
   POST /api/convert-lead {intel_id,name,phone}
   GET  /api/export-leads  POST /api/scrape-now
   GET  /api/sources  GET /api/scheduler
*/

'use strict';

const state = {
  tab: 'overview',
  intel: [],
  leads: [],
  stats: null,
  sourceMeta: {},   // key -> {label, icon, desc}
  intentFilter: 'all',
  search: '',
  pitchItem: null,
  convertId: null,
};

const itemIndex = new Map(); // intel id -> item

/* ── Small helpers ────────────────────────────────────────── */
const $ = (id) => document.getElementById(id);

function escHtml(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
                  .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function fmtNum(n) {
  const v = Number(n) || 0;
  return v.toLocaleString('en-IN');
}

function fmtDate(dt) {
  if (!dt) return 'Just now';
  try {
    const d = new Date(dt);
    if (isNaN(d.getTime())) return String(dt).slice(0, 16);
    const now = Date.now();
    const diff = now - d.getTime();
    if (diff < 0) return 'Just now';
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'Just now';
    if (mins < 60) return mins + 'm ago';
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return hrs + 'h ago';
    return d.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' }) + ', ' +
           d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
  } catch (e) { return String(dt); }
}

function extraOf(item) {
  if (!item || !item.extra_json) return {};
  try { return JSON.parse(item.extra_json) || {}; } catch (e) { return {}; }
}

/* ── Toasts ───────────────────────────────────────────────── */
const ICONS = {
  ok:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>',
  err:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M12 8v5"/><circle cx="12" cy="12" r="9"/><path d="M12 16.5h.01"/></svg>',
  info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 7.5h.01"/></svg>',
};

function toast(msg, type = 'ok', sub = '') {
  const box = $('toasts');
  if (!box) return;
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.innerHTML = '<span class="t-ico">' + (ICONS[type] || ICONS.info) + '</span>' +
                 '<div><div>' + escHtml(msg) + '</div>' +
                 (sub ? '<small>' + escHtml(sub) + '</small>' : '') + '</div>';
  box.appendChild(el);
  setTimeout(() => {
    el.classList.add('out');
    setTimeout(() => el.remove(), 280);
  }, 4200);
}

/* ── Tabs ─────────────────────────────────────────────────── */
const TITLES = {
  overview: 'Overview',
  intelligence: 'Live Feed',
  leads: 'Call Queue',
  scraper: 'Sources & Engine',
};

function showTab(name) {
  document.querySelectorAll('.tab-section').forEach(s => s.classList.add('hidden'));
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  const sec = $('tab-' + name);
  const btn = $('tab-btn-' + name);
  if (sec) sec.classList.remove('hidden');
  if (btn) btn.classList.add('active');
  const t = $('pageTitle');
  if (t) t.textContent = TITLES[name] || name;
  state.tab = name;
  document.body.classList.remove('nav-open');
  if (name === 'overview') loadOverview();
  else if (name === 'intelligence') loadIntelligence();
  else if (name === 'leads') loadLeads();
  else if (name === 'scraper') loadSources();
}

/* ── Intent ───────────────────────────────────────────────── */
function resolveIntent(item) {
  // 1) Backend-provided fields (preferred). Accepts "high"/"medium"/"low"
  //    as well as legacy label strings.
  const raw = item.intent_level ?? item.intent ?? null;
  const scoreRaw = item.intent_score ?? item.score ?? null;
  const score = (scoreRaw === null || scoreRaw === undefined || scoreRaw === '')
    ? null : Math.max(0, Math.min(100, Math.round(Number(scoreRaw) || 0)));
  if (raw !== null && raw !== undefined && String(raw).trim() !== '') {
    const l = String(raw).toLowerCase();
    if (l.includes('high') || l === '3' || l === 'hot')  return { level: 'high', score };
    if (l.includes('med') || l.includes('active') || l === '2' || l === 'warm') return { level: 'medium', score };
    if (l.includes('low') || l.includes('explor') || l === '1' || l === 'cold') return { level: 'low', score };
  }
  // 2) Client-side heuristic fallback (keeps UI useful until backend ships scoring)
  const t = ((item.title || '') + ' ' + (item.snippet || '')).toLowerCase();
  if (/(percentile|cutoff|cut-off|shortlist|admission|apply|deadline|counselling|counseling|calls?\b|score|converted|waitlist)/.test(t))
    return { level: 'high', score: null };
  if (/(which college|fees|fee|placement|package|gd|pi\b|interview|compare|vs\.? |better|worth|syllabus|mock|preparation|prep\b)/.test(t))
    return { level: 'medium', score: null };
  return { level: 'low', score: null };
}

function intentBadge(item) {
  const { level, score } = resolveIntent(item);
  const label = level === 'high' ? 'High intent' : level === 'medium' ? 'Medium' : 'Exploring';
  let html = '<span class="intent-badge intent-' + level + '">' + label + '</span>';
  if (score !== null) html += '<span class="intent-score" title="Intent score">' + score + '</span>';
  item._intentLevel = level; // cache for filtering
  return html;
}

function setIntentFilter(level, btn) {
  state.intentFilter = level;
  document.querySelectorAll('.seg button').forEach(b => b.classList.remove('on'));
  if (btn) btn.classList.add('on');
  renderIntelCards('intelGrid', filteredIntel());
}

/* ── Source labels ────────────────────────────────────────── */
const SOURCE_FALLBACK = {
  reddit: 'Reddit', pagalguy: 'Pagalguy', google_news: 'Google News',
  google_trends: 'Google Trends', college_portal: 'College Portal',
  quora: 'Quora', shiksha: 'Shiksha', careers360: 'Careers360',
  mba_universe: 'MBA Universe', collegedunia: 'CollegeDunia',
  youtube: 'YouTube', telegram: 'Telegram', india_news: 'India News',
};

function sourceBadge(src) {
  const meta = state.sourceMeta[src];
  const icon = meta && meta.icon ? '<span class="src-ico">' + escHtml(meta.icon) + '</span>' : '';
  const label = meta && meta.label ? meta.label : (SOURCE_FALLBACK[src] || src || 'Web');
  return '<span class="src-badge">' + icon + escHtml(label) + '</span>';
}

async function ensureSources() {
  if (Object.keys(state.sourceMeta).length) return;
  try {
    const res = await fetch('/api/sources');
    const list = await res.json();
    list.forEach(s => { state.sourceMeta[s.key] = s; });
    // Populate the source filter dropdown once
    const sel = $('sourceFilter');
    if (sel && sel.options.length <= 1) {
      list.forEach(s => {
        const o = document.createElement('option');
        o.value = s.key;
        o.textContent = (s.icon ? s.icon + ' ' : '') + s.label;
        sel.appendChild(o);
      });
    }
  } catch (e) { /* non-fatal */ }
}

/* ── Overview ─────────────────────────────────────────────── */
async function loadOverview() {
  const grid = $('overviewIntelGrid');
  if (grid && !state.intel.length) grid.innerHTML = '<div class="skel"></div>'.repeat(3);
  try {
    await ensureSources();
    const [statsRes, intelRes] = await Promise.all([
      fetch('/api/stats'),
      fetch('/api/intelligence?limit=120'),
    ]);
    const stats = await statsRes.json();
    const intel = await intelRes.json();
    state.stats = stats;
    state.intel = intel;
    intel.forEach(i => itemIndex.set(i.id, i));

    $('sc-intel').textContent = fmtNum(stats.intel_total || intel.length || 0);
    $('sc-intel-delta').textContent = '+' + fmtNum(stats.intel_today || 0) + ' today';

    $('sc-total').textContent = fmtNum(stats.total || 0);
    $('sc-today').textContent = '+' + fmtNum(stats.today || 0) + ' today';

    const examRows = stats.by_exam || stats.intel_by_exam || [];
    const top = examRows[0];
    $('sc-top-exam').textContent = top ? (top.target_exam || top.exam || '—') : '—';
    $('sc-exam-delta').textContent = top ? fmtNum(top.cnt) + ' signals' : '—';
    $('sc-exam-count').textContent = 'Top target exam';

    const srcCount = $('sc-sources-count');
    if (srcCount) srcCount.textContent = Object.keys(state.sourceMeta).length || '—';

    const nb1 = $('navIntelCount'); if (nb1) nb1.textContent = fmtNum(stats.intel_total || 0);
    const nb2 = $('navLeadCount'); if (nb2) nb2.textContent = fmtNum(stats.total || 0);

    renderBarChart('examChart', examRows, ['target_exam', 'exam'], 'cnt',
      'linear-gradient(90deg,#6c7bff,#8b5cf6)');
    renderBarChart('sourceChart', stats.intel_by_source || [], ['source'], 'cnt',
      'linear-gradient(90deg,#22d3ee,#6c7bff)', true);

    renderIntelCards('overviewIntelGrid', intel.slice(0, 6));
    updateEngineStatus(stats);
  } catch (err) {
    console.error('Overview load error:', err);
    if (grid) grid.innerHTML = errorState('Could not load overview', 'Check that the Flask server is running and retry.');
  }
}

function renderBarChart(containerId, data, labelKeys, valueKey, gradient, mapSource) {
  const c = $(containerId);
  if (!c) return;
  if (!data || !data.length) {
    c.innerHTML = '<div class="bar-empty">Collecting data points…</div>';
    return;
  }
  const rows = data.slice(0, 7);
  const max = Math.max.apply(null, rows.map(d => Number(d[valueKey]) || 0).concat([1]));
  c.innerHTML = rows.map(d => {
    const val = Number(d[valueKey]) || 0;
    let label = '—';
    for (const k of labelKeys) { if (d[k]) { label = d[k]; break; } }
    if (mapSource) {
      const meta = state.sourceMeta[label];
      label = meta ? meta.label : (SOURCE_FALLBACK[label] || label);
    }
    const pct = Math.max(Math.round((val / max) * 100), 6);
    return '<div class="bar-row">' +
      '<div class="bar-label" title="' + escHtml(String(label)) + '">' + escHtml(String(label)) + '</div>' +
      '<div class="bar-track"><div class="bar-fill" style="width:' + pct + '%;background:' + gradient + '">' +
      '<span class="num">' + fmtNum(val) + '</span></div></div></div>';
  }).join('');
}

function updateEngineStatus(stats) {
  const sched = (stats && stats.scheduler) || {};
  const dot = $('engineDot'), label = $('engineLabel'), sub = $('engineSub');
  const running = !!sched.running;
  if (dot) dot.classList.toggle('off', !running);
  if (label) label.textContent = running ? 'Engine active' : 'Engine idle';
  if (sub) sub.textContent = sched.last_run ? ('Last sync: ' + sched.last_run)
    : (stats && stats.last_scrape && stats.last_scrape !== 'Never' ? ('Last sync: ' + stats.last_scrape) : 'Starting…');
}

/* ── Intelligence feed ────────────────────────────────────── */
function filteredIntel() {
  let items = state.intel.slice();
  if (state.intentFilter !== 'all') {
    items = items.filter(i => resolveIntent(i).level === state.intentFilter);
  }
  if (state.search) {
    const q = state.search.toLowerCase();
    items = items.filter(i =>
      (i.title && i.title.toLowerCase().includes(q)) ||
      (i.snippet && i.snippet.toLowerCase().includes(q)) ||
      (i.exam_hint && i.exam_hint.toLowerCase().includes(q)) ||
      (i.college && i.college.toLowerCase().includes(q)) ||
      (i.city_hint && i.city_hint.toLowerCase().includes(q)) ||
      (i.source && i.source.toLowerCase().includes(q)));
  }
  return items;
}

async function loadIntelligence() {
  const source = $('sourceFilter') ? $('sourceFilter').value : 'all';
  const exam = $('intelExamFilter') ? $('intelExamFilter').value : 'all';
  const grid = $('intelGrid');
  if (grid) grid.innerHTML = '<div class="skel"></div>'.repeat(6);
  try {
    await ensureSources();
    const res = await fetch('/api/intelligence?source=' + encodeURIComponent(source) +
                            '&exam=' + encodeURIComponent(exam) + '&limit=200');
    const items = await res.json();
    state.intel = items;
    itemIndex.clear();
    items.forEach(i => itemIndex.set(i.id, i));
    const badge = $('intelCountBadge');
    if (badge) badge.textContent = fmtNum(items.length) + ' signals loaded';
    renderIntelCards('intelGrid', filteredIntel());
  } catch (err) {
    if (grid) grid.innerHTML = errorState('Feed failed to load', 'The server may be busy — try the Scrape now button or reload.');
  }
}

function renderIntelCards(containerId, items) {
  const grid = $(containerId);
  if (!grid) return;
  if (!items || !items.length) {
    grid.innerHTML = '<div class="state-msg">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>' +
      '<strong>No signals match</strong>Try a different filter, or run a fresh scrape.</div>';
    return;
  }
  grid.innerHTML = items.map(cardHtml).join('');
}

function cardHtml(item) {
  const extra = extraOf(item);
  const context = extra.subreddit ? 'r/' + extra.subreddit
    : extra.channel ? '@' + extra.channel : null;
  const tags = [];
  if (item.exam_hint) tags.push('<span class="tag exam">' + escHtml(item.exam_hint) + '</span>');
  if (item.city_hint) tags.push('<span class="tag city">' + escHtml(item.city_hint) + '</span>');
  if (item.college) tags.push('<span class="tag college">' + escHtml(item.college) + '</span>');
  if (context) tags.push('<span class="tag">' + escHtml(context) + '</span>');

  const snippet = item.snippet
    ? '<p class="ic-snippet">' + escHtml(item.snippet.length > 220 ? item.snippet.slice(0, 220) + '…' : item.snippet) + '</p>' : '';

  return '<article class="intel-card">' +
    '<div class="ic-top"><div class="ic-badges">' + sourceBadge(item.source) + intentBadge(item) + '</div>' +
    '<span class="ic-time">' + escHtml(fmtDate(item.scraped_at)) + '</span></div>' +
    '<h4 class="ic-title">' + escHtml(item.title || 'Aspirant signal') + '</h4>' +
    snippet +
    (tags.length ? '<div class="ic-tags">' + tags.join('') + '</div>' : '') +
    '<div class="ic-actions">' +
      '<button class="chip-btn pitch" onclick="openPitchModal(' + item.id + ')">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/></svg>' +
        'Pitch script</button>' +
      '<button class="chip-btn convert" onclick="openConvertModal(' + item.id + ')">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>' +
        'Add to CRM</button>' +
      (item.url ? '<a class="chip-btn view" href="' + escHtml(item.url) + '" target="_blank" rel="noopener" title="Open source">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6"/><path d="M10 14 21 3"/></svg>' +
        'Source</a>' : '') +
    '</div></article>';
}

function errorState(title, sub) {
  return '<div class="state-msg">' +
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 8v5"/><path d="M12 16.5h.01"/></svg>' +
    '<strong>' + escHtml(title) + '</strong>' + escHtml(sub) + '</div>';
}

/* ── Search ───────────────────────────────────────────────── */
function handleSearch(q) {
  state.search = (q || '').trim();
  if (state.tab === 'overview') renderIntelCards('overviewIntelGrid', filteredIntel().slice(0, 6));
  else if (state.tab === 'intelligence') {
    renderIntelCards('intelGrid', filteredIntel());
    const badge = $('intelCountBadge');
    if (badge) badge.textContent = fmtNum(filteredIntel().length) + ' matches';
  }
}

/* ── Pitch modal ──────────────────────────────────────────── */
function openPitchModal(id) {
  const item = itemIndex.get(id);
  if (!item) return;
  state.pitchItem = item;
  const exam = item.exam_hint || 'MBA';
  const college = item.college || 'top AICTE-approved B-schools';
  const srcMeta = state.sourceMeta[item.source];
  const srcName = srcMeta ? srcMeta.label : (SOURCE_FALLBACK[item.source] || 'the web');

  $('pmTitle').textContent = 'Call pitch — ' + exam + ' aspirant';
  $('pmExamTag').textContent = 'Signal from ' + srcName + (item.city_hint ? ' · ' + item.city_hint : '');
  $('pmQueryText').textContent = (item.title || '') + (item.snippet ? ' — ' + item.snippet.slice(0, 280) : '');

  $('pmGeneratedScript').innerHTML =
    '<p><strong>1 · Open warm</strong><br>' +
    '“Hi, I noticed you were looking into <strong>' + escHtml(exam) + '</strong> admissions' +
    (item.college ? ' at <strong>' + escHtml(item.college) + '</strong>' : '') +
    '. I’m calling from EduPulse — we help aspirants shortlist colleges for free. Do you have two minutes?”</p>' +
    '<p><strong>2 · Diagnose</strong><br>' +
    '“What stage are you at — still preparing, or already checking cutoffs and applications for ' +
    escHtml(college) + '?”</p>' +
    '<p><strong>3 · Value</strong><br>' +
    '“Based on your profile we can share a personalised shortlist — expected cutoffs, fee vs. placement comparison, ' +
    'and scholarship options you may be eligible for. It’s free, no spam.”</p>' +
    '<p><strong>4 · Close</strong><br>' +
    '“Shall I send the shortlist and cutoff sheet on WhatsApp right now? What’s the best number?”</p>';

  $('pitchModal').classList.remove('hidden');
}
function closePitchModal() {
  $('pitchModal').classList.add('hidden');
  state.pitchItem = null;
}
function copyPitchScript() {
  const box = $('pmGeneratedScript');
  if (!box) return;
  const text = box.innerText || box.textContent;
  const done = () => toast('Script copied to clipboard');
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
  } else fallbackCopy(text, done);
}
function fallbackCopy(text, done) {
  const ta = document.createElement('textarea');
  ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
  document.body.appendChild(ta); ta.select();
  try { document.execCommand('copy'); done(); } catch (e) { toast('Copy failed', 'err'); }
  ta.remove();
}
function convertCurrentToLead() {
  if (!state.pitchItem) return;
  const id = state.pitchItem.id;
  closePitchModal();
  openConvertModal(id);
}

/* ── Convert modal ────────────────────────────────────────── */
function openConvertModal(id) {
  const item = itemIndex.get(id);
  state.convertId = id;
  $('cmSub').textContent = item ? ('From: ' + (item.title || 'signal').slice(0, 70)) : '';
  $('cmName').value = '';
  $('cmPhone').value = '';
  $('convertModal').classList.remove('hidden');
  setTimeout(() => $('cmName').focus(), 60);
}
function closeConvertModal() {
  $('convertModal').classList.add('hidden');
  state.convertId = null;
}
async function submitConvert() {
  const id = state.convertId;
  if (!id) return;
  const name = $('cmName').value.trim();
  const phone = $('cmPhone').value.trim();
  try {
    const res = await fetch('/api/convert-lead', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ intel_id: id, name, phone }),
    });
    const data = await res.json();
    if (data.ok) {
      closeConvertModal();
      toast('Added to call queue', 'ok', 'Lead #' + data.lead_id + ' is ready for counseling.');
      if (state.tab === 'leads') loadLeads();
      else loadOverview();
    } else {
      toast('Could not convert lead', 'err', data.error || 'Unknown error');
    }
  } catch (err) {
    toast('Could not convert lead', 'err', err.message);
  }
}

/* ── Call queue ───────────────────────────────────────────── */
function normPhone(p) {
  if (!p) return null;
  const d = String(p).replace(/\D/g, '');
  if (!d || /pending/i.test(String(p))) return null;
  if (d.length === 10 && /^[6-9]/.test(d)) return '91' + d;
  if (d.length === 12 && d.startsWith('91')) return d;
  if (d.length > 7) return d;
  return null;
}

async function loadLeads() {
  const exam = $('examFilter') ? $('examFilter').value : 'all';
  const body = $('leadsTableBody');
  if (body) body.innerHTML = '<div style="padding:34px;text-align:center;color:var(--muted);font-size:0.85rem">Loading call queue…</div>';
  try {
    const res = await fetch('/api/leads?exam=' + encodeURIComponent(exam) + '&limit=200');
    const leads = await res.json();
    state.leads = leads;
    const c = $('leadsCount');
    if (c) c.textContent = fmtNum(leads.length) + ' in queue';
    const nb = $('navLeadCount'); if (nb) nb.textContent = fmtNum(leads.length);
    renderLeadsTable(leads);
  } catch (err) {
    if (body) body.innerHTML = '<div style="padding:34px;text-align:center;color:var(--muted);font-size:0.85rem">Failed to load leads.</div>';
  }
}

function renderLeadsTable(leads) {
  const body = $('leadsTableBody');
  if (!body) return;
  if (!leads.length) {
    body.innerHTML = '<div style="padding:44px 20px;text-align:center;color:var(--muted);font-size:0.88rem">' +
      '<div style="font-weight:800;color:var(--text-2);margin-bottom:6px">Queue is empty</div>' +
      'Convert a signal from the Live Feed with “Add to CRM” and it will appear here.</div>';
    return;
  }
  const rows = leads.map(l => {
    const ph = normPhone(l.phone);
    const callBtn = ph
      ? '<a class="icon-btn" href="tel:+' + ph + '" title="Call ' + escHtml(l.name) + '"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/></svg></a>'
      : '<span class="icon-btn disabled" title="No phone number yet"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/></svg></span>';
    const waBtn = ph
      ? '<a class="icon-btn wa" href="https://wa.me/' + ph + '" target="_blank" rel="noopener" title="WhatsApp ' + escHtml(l.name) + '"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg></a>'
      : '';
    return '<tr>' +
      '<td><span class="lead-id">#' + l.id + '</span></td>' +
      '<td><span class="lead-name">' + escHtml(l.name) + '</span></td>' +
      '<td><span class="lead-phone num">' + escHtml(l.phone || '—') + '</span></td>' +
      '<td><span class="exam-pill">' + escHtml(l.target_exam || 'CAT') + '</span></td>' +
      '<td style="color:var(--muted)">' + escHtml(l.city || '—') + '</td>' +
      '<td style="color:var(--faint);font-size:0.76rem">' + escHtml(l.utm || l.source || '—') + '</td>' +
      '<td><span class="status-pill">' + (l.whatsapp_sent ? 'Contacted' : 'Ready to call') + '</span></td>' +
      '<td><div class="row-actions">' + callBtn + waBtn + '</div></td>' +
    '</tr>';
  }).join('');
  body.innerHTML = '<table class="leads"><thead><tr>' +
    '<th>ID</th><th>Candidate</th><th>Phone</th><th>Exam</th><th>City</th><th>Origin</th><th>Status</th><th>Actions</th>' +
    '</tr></thead><tbody>' + rows + '</tbody></table>';
}

/* ── Sources tab ──────────────────────────────────────────── */
async function loadSources() {
  try {
    await ensureSources();
    const [statsRes] = await Promise.all([fetch('/api/stats')]);
    const stats = await statsRes.json();
    const sched = stats.scheduler || {};

    $('ss-status').textContent = sched.running ? 'Active' : 'Idle';
    $('ss-status').style.color = sched.running ? 'var(--emerald)' : 'var(--amber)';
    $('ss-last-run').textContent = sched.last_run
      ? 'Last sweep: ' + sched.last_run + ' · +' + fmtNum(sched.last_added || 0) + ' new'
      : 'Waiting for first sweep…';
    $('ss-total').textContent = fmtNum(stats.intel_total || 0);
    $('ss-added').textContent = '+' + fmtNum(stats.intel_today || 0) + ' collected today';

    const counts = {};
    (stats.intel_by_source || []).forEach(r => { counts[r.source] = r.cnt; });
    const keys = Object.keys(state.sourceMeta);
    $('sourceCount').textContent = keys.length + ' engines configured';
    $('sourcesList').innerHTML = keys.map(k => {
      const m = state.sourceMeta[k];
      const n = counts[k];
      return '<div class="source-card">' +
        '<div class="source-ico">' + escHtml(m.icon || '◈') + '</div>' +
        '<div class="source-meta"><h4>' + escHtml(m.label) + '</h4>' +
        '<p>' + escHtml(m.desc || '') + '</p>' +
        (n !== undefined ? '<span class="source-count num">' + fmtNum(n) + ' signals stored</span>' : '') +
        '</div><span class="live-tag">Live</span></div>';
    }).join('');
    updateEngineStatus(stats);
  } catch (err) {
    console.error('Sources load error:', err);
  }
}

/* ── Manual scrape / exports ──────────────────────────────── */
async function triggerScrape() {
  const btn = $('scrapeBtn');
  const orig = btn ? btn.innerHTML : '';
  if (btn) { btn.disabled = true; btn.innerHTML = 'Scraping…'; }
  try {
    const res = await fetch('/api/scrape-now', { method: 'POST' });
    const data = await res.json();
    toast('Scrape started in background', 'info', 'Fresh signals will appear in ~60 seconds.');
    setTimeout(() => {
      if (state.tab === 'overview') loadOverview();
      else if (state.tab === 'intelligence') loadIntelligence();
      else if (state.tab === 'scraper') loadSources();
    }, 45000);
  } catch (err) {
    toast('Could not trigger scrape', 'err', err.message);
  } finally {
    setTimeout(() => { if (btn) { btn.disabled = false; btn.innerHTML = orig; } }, 3000);
  }
}

function exportIntelligenceCSV() {
  window.location.href = '/api/export-leads';
  toast('Preparing CSV download', 'info', 'Your browser will download the file shortly.');
}

function csvCell(v) {
  const s = String(v === null || v === undefined ? '' : v);
  return '"' + s.replace(/"/g, '""') + '"';
}

async function exportCRMLeads() {
  try {
    const res = await fetch('/api/leads?limit=500');
    const leads = await res.json();
    if (!leads.length) { toast('Call queue is empty', 'err', 'Convert signals from the Live Feed first.'); return; }
    const rows = [['ID', 'Name', 'Phone', 'Email', 'City', 'Target Exam', 'Target Year', 'Origin', 'Created At']];
    leads.forEach(l => rows.push([
      l.id, l.name, l.phone, l.email || '', l.city || '',
      l.target_exam || '', l.target_year || '', l.utm || l.source || '', l.created_at || '',
    ]));
    const csv = rows.map(r => r.map(csvCell).join(',')).join('\r\n');
    const blob = new Blob(["\uFEFF" + csv], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'edupulse_call_queue_' + new Date().toISOString().slice(0, 10) + '.csv';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    toast('Call queue exported', 'ok', fmtNum(leads.length) + ' leads downloaded.');
  } catch (err) {
    toast('Export failed', 'err', err.message);
  }
}

/* ── Keyboard / auto-refresh / boot ───────────────────────── */
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closePitchModal();
    closeConvertModal();
    document.body.classList.remove('nav-open');
  }
});

setInterval(() => {
  if (document.hidden) return;
  if (state.tab === 'overview') loadOverview();
  else if (state.tab === 'intelligence') loadIntelligence();
  else if (state.tab === 'scraper') loadSources();
}, 30000);

document.addEventListener('DOMContentLoaded', () => {
  loadOverview();
});
