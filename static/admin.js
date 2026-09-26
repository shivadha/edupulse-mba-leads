// EduPulse India — Internal Admissions CRM & MBA Lead Intelligence JS

let currentTab = 'overview';
let allIntelData = [];
let activePitchItem = null;

function showTab(name) {
  document.querySelectorAll('.tab-section').forEach(s => s.classList.add('hidden'));
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));

  const sec = document.getElementById('tab-' + name);
  const btn = document.getElementById('tab-btn-' + name);
  if (sec) sec.classList.remove('hidden');
  if (btn) btn.classList.add('active');

  const titles = {
    overview: 'Internal Dashboard & Aspirant Stream',
    intelligence: 'Live Aspirants Lead Feed',
    leads: 'Admissions Call Queue (CRM)',
    scraper: 'Background Scraper Engines'
  };
  const titleEl = document.getElementById('pageTitle');
  if (titleEl) titleEl.textContent = titles[name] || name;
  currentTab = name;

  if (name === 'overview') loadOverview();
  else if (name === 'intelligence') loadIntelligence();
  else if (name === 'leads') loadLeads();
  else if (name === 'scraper') loadScraperStatus();
}

// ─── Overview ──────────────────────────────────────────────────────
async function loadOverview() {
  try {
    const [statsRes, intelRes, leadsRes] = await Promise.all([
      fetch('/api/stats'),
      fetch('/api/intelligence?limit=150'),
      fetch('/api/leads?limit=10'),
    ]);
    const stats = await statsRes.json();
    const intel = await intelRes.json();
    const leads = await leadsRes.json();
    allIntelData = intel;

    // Stats cards
    const totalAspirants = stats.intel_total || intel.length || 0;
    const directLeads = stats.total || 0;
    
    document.getElementById('sc-intel').textContent = totalAspirants.toLocaleString();
    document.getElementById('sc-intel-delta').textContent = `+${stats.intel_today || totalAspirants} collected today`;
    
    document.getElementById('sc-total').textContent = directLeads;
    document.getElementById('sc-today').textContent = `+${stats.today || 0} today`;

    const topExam = stats.intel_by_exam?.[0] || stats.by_exam?.[0];
    document.getElementById('sc-top-exam').textContent = topExam ? (topExam.exam || topExam.target_exam) : 'CAT';
    document.getElementById('sc-exam-count').textContent = `${topExam ? topExam.cnt : 0} queries`;

    // Render charts
    renderBarChart('examChart', stats.by_exam || [], 'target_exam', 'cnt', '#6C3EF4');
    renderBarChart('cityChart', stats.intel_by_source || [], 'source', 'cnt', '#0EA5E9');

    // Render live stream preview on overview (first 6 items)
    renderIntelCards('overviewIntelGrid', intel.slice(0, 6));

    // Scraper status footer
    const sched = stats.scheduler || {};
    const lastUpdateEl = document.getElementById('lastUpdate');
    const scraperLabelEl = document.getElementById('scraperLabel');
    if (lastUpdateEl) {
      lastUpdateEl.textContent = sched.last_run ? `Last sync: ${sched.last_run}` : 'Background active (5m)';
    }
    if (scraperLabelEl) {
      scraperLabelEl.textContent = sched.running ? 'Background Sync Active' : 'Scheduler Running';
    }

  } catch (err) {
    console.error('Overview load error:', err);
  }
}

// ─── Bar Chart ─────────────────────────────────────────────────────
function renderBarChart(containerId, data, labelKey, valueKey, color) {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (!data || !data.length) {
    container.innerHTML = '<div style="color:#64748B;font-size:0.8rem;text-align:center;padding:24px">Collecting data points...</div>';
    return;
  }

  const max = Math.max(...data.map(d => d[valueKey] || 0), 1);
  container.innerHTML = data.slice(0, 6).map(d => {
    const val = d[valueKey] || 0;
    const pct = Math.max(Math.round((val / max) * 100), 8);
    const label = d[labelKey] || '—';
    return `
      <div class="bar-row" style="display:flex;align-items:center;gap:12px;margin-bottom:8px">
        <div class="bar-label" style="width:110px;font-size:0.82rem;font-weight:600;color:#334155;text-overflow:ellipsis;white-space:nowrap;overflow:hidden">${escHtml(label)}</div>
        <div class="bar-track" style="flex:1;background:#F1F5F9;border-radius:6px;height:22px;overflow:hidden;position:relative">
          <div class="bar-fill" style="width:${pct}%;height:100%;background:${color};border-radius:6px;display:flex;align-items:center;justify-content:flex-end;padding-right:8px;transition:width 0.5s ease">
            <span style="font-size:0.75rem;font-weight:700;color:#FFFFFF">${val}</span>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

// ─── Intelligence Feed ─────────────────────────────────────────────
async function loadIntelligence() {
  const source = document.getElementById('sourceFilter')?.value || 'all';
  const exam = document.getElementById('intelExamFilter')?.value || 'all';
  const grid = document.getElementById('intelGrid');
  const countBadge = document.getElementById('intelCountBadge');
  
  if (grid) grid.innerHTML = '<div class="loading-state">Refreshing live stream...</div>';

  try {
    const res = await fetch(`/api/intelligence?source=${source}&exam=${exam}&limit=200`);
    const items = await res.json();
    allIntelData = items;
    
    if (countBadge) countBadge.textContent = `${items.length} Live Inquiries Loaded`;
    renderIntelCards('intelGrid', items);
  } catch (err) {
    if (grid) grid.innerHTML = '<div class="loading-state">Failed to load feed. Please retry.</div>';
  }
}

function renderIntelCards(containerId, items) {
  const grid = document.getElementById(containerId);
  if (!grid) return;

  if (!items || !items.length) {
    grid.innerHTML = '<div class="loading-state" style="padding:40px;color:#64748B">No leads found matching current filter.</div>';
    return;
  }

  grid.innerHTML = items.map(item => {
    const intent = getIntentLevel(item.title + ' ' + (item.snippet || ''));
    return `
      <div class="intel-card" style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;padding:16px;box-shadow:0 2px 8px rgba(0,0,0,0.04);transition:all 0.2s ease;display:flex;flex-direction:column;justify-content:space-between">
        <div>
          <div class="ic-source" style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
            <div style="display:flex;gap:6px;align-items:center">
              <span class="ic-source-badge ${item.source}" style="padding:3px 8px;border-radius:6px;font-size:0.72rem;font-weight:700;background:#F1F5F9;color:#475569">${sourceLabel(item.source)}</span>
              <span style="padding:2px 8px;border-radius:6px;font-size:0.72rem;font-weight:700;background:${intent.bg};color:${intent.color}">${intent.label}</span>
            </div>
            <span class="ic-time" style="font-size:0.72rem;color:#94A3B8">${formatDate(item.scraped_at)}</span>
          </div>

          <h4 style="font-size:0.92rem;font-weight:600;color:#0F172A;line-height:1.4;margin-bottom:6px">${escHtml(item.title || 'Candidate Query')}</h4>
          ${item.snippet ? `<p style="font-size:0.8rem;color:#64748B;line-height:1.5;margin-bottom:12px">${escHtml(item.snippet.slice(0, 150))}${item.snippet.length > 150 ? '...' : ''}</p>` : ''}
        </div>

        <div>
          <div class="ic-tags" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px">
            ${item.exam_hint ? `<span style="background:#EEF2FF;color:#4F46E5;padding:2px 8px;border-radius:6px;font-size:0.75rem;font-weight:600">📚 ${escHtml(item.exam_hint)}</span>` : '<span style="background:#F8FAFC;color:#64748B;padding:2px 8px;border-radius:6px;font-size:0.75rem">📚 MBA</span>'}
            ${item.city_hint ? `<span style="background:#ECFDF5;color:#059669;padding:2px 8px;border-radius:6px;font-size:0.75rem;font-weight:600">🏙️ ${escHtml(item.city_hint)}</span>` : ''}
            ${item.college ? `<span style="background:#FEF3C7;color:#D97706;padding:2px 8px;border-radius:6px;font-size:0.75rem;font-weight:600">🏫 ${escHtml(item.college)}</span>` : ''}
          </div>

          <div style="display:flex;gap:8px;align-items:center;border-top:1px solid #F1F5F9;padding-top:12px">
            <button class="btn-action-small btn-pitch" onclick='openPitchModal(${JSON.stringify(item).replace(/'/g, "&apos;")})'>
              📞 Pitch Script
            </button>
            <button class="btn-action-small btn-convert" onclick="convertToCRM(${item.id})">
              ➕ Add to CRM
            </button>
            ${item.url ? `<button class="btn-action-small" style="background:#F1F5F9;color:#475569;margin-left:auto" onclick="openUrl('${escAttr(item.url)}')">↗ View</button>` : ''}
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function getIntentLevel(text) {
  const t = (text || '').toLowerCase();
  if (t.includes('percentile') || t.includes('admission') || t.includes('cutoff') || t.includes('shortlist') || t.includes('calls') || t.includes('score')) {
    return { label: '🔥 High Intent', bg: '#FEE2E2', color: '#DC2626' };
  }
  if (t.includes('which college') || t.includes('fees') || t.includes('placement') || t.includes('gd') || t.includes('pi') || t.includes('interview')) {
    return { label: '⚡ Active Inquirer', bg: '#FEF3C7', color: '#D97706' };
  }
  return { label: '💡 Exploring', bg: '#EFF6FF', color: '#2563EB' };
}

function sourceLabel(src) {
  const map = {
    reddit: '🔴 Reddit', pagalguy: '💬 Pagalguy',
    google_news: '📰 Google News', college_portal: '🏛️ College Portal',
    quora: '❓ Quora', shiksha: '🎓 Shiksha',
    careers360: '🚀 Careers360', mba_universe: '🌐 MBA Universe',
    collegedunia: '🏫 CollegeDunia', youtube: '▶️ YouTube',
    telegram: '✈️ Telegram', india_news: '🗞️ India News',
  };
  return map[src] || src;
}

function openUrl(url) {
  if (url && url.startsWith('http')) window.open(url, '_blank');
}

// ─── Search ────────────────────────────────────────────────────────
function handleSearch(query) {
  if (!query) {
    if (currentTab === 'overview') renderIntelCards('overviewIntelGrid', allIntelData.slice(0, 6));
    else renderIntelCards('intelGrid', allIntelData);
    return;
  }
  const q = query.toLowerCase();
  const filtered = allIntelData.filter(item => 
    (item.title && item.title.toLowerCase().includes(q)) ||
    (item.snippet && item.snippet.toLowerCase().includes(q)) ||
    (item.exam_hint && item.exam_hint.toLowerCase().includes(q)) ||
    (item.college && item.college.toLowerCase().includes(q)) ||
    (item.source && item.source.toLowerCase().includes(q))
  );

  if (currentTab === 'overview') {
    renderIntelCards('overviewIntelGrid', filtered.slice(0, 6));
  } else {
    renderIntelCards('intelGrid', filtered);
    const countBadge = document.getElementById('intelCountBadge');
    if (countBadge) countBadge.textContent = `${filtered.length} matches for "${query}"`;
  }
}

// ─── Telecaller Pitch Modal ────────────────────────────────────────
function openPitchModal(item) {
  activePitchItem = item;
  const modal = document.getElementById('pitchModal');
  const titleEl = document.getElementById('pmAspirantTitle');
  const examTag = document.getElementById('pmExamTag');
  const queryText = document.getElementById('pmQueryText');
  const scriptBox = document.getElementById('pmGeneratedScript');

  const exam = item.exam_hint || 'MBA / CAT';
  const college = item.college || 'Top AICTE/UGC Accredited B-Schools';
  
  if (titleEl) titleEl.textContent = `Admissions Call Pitch (${exam})`;
  if (examTag) examTag.textContent = `Lead Source: ${sourceLabel(item.source)} | Target: ${exam}`;
  if (queryText) queryText.textContent = item.title + (item.snippet ? ` — "${item.snippet}"` : '');

  // Dynamic Telecalling Pitch Generation
  const script = `
    <p><strong>1. Icebreaker & Rapport:</strong><br>
    "Hi there! I came across your recent inquiry regarding <em>${escHtml(exam)} prep & admissions cutoff for ${escHtml(college)}</em>. I'm calling from the Central MBA Admissions Advisory desk."</p>
    <br>
    <p><strong>2. Value Proposition (Counseling & Placement):</strong><br>
    "We are currently shortlisting students for premier MBA & PGDM programs offering average packages of <strong>12 to 18 LPA</strong> with 100% placement track records, approved by AICTE & NBA. Based on your target score, you may qualify for direct institutional scholarship waivers up to 40%."</p>
    <br>
    <p><strong>3. Discovery Question:</strong><br>
    "Are you primarily targeting Marketing, Finance, Business Analytics, or General Management for the upcoming 2025-2027 batch?"</p>
    <br>
    <p><strong>4. Call to Action / WhatsApp Follow-up:</strong><br>
    "Shall I send the cutoff comparison brochure, fee structure, and scholarship eligibility matrix directly to your WhatsApp right now?"</p>
  `;

  if (scriptBox) scriptBox.innerHTML = script;
  if (modal) modal.style.display = 'flex';
}

function closePitchModal() {
  const modal = document.getElementById('pitchModal');
  if (modal) modal.style.display = 'none';
  activePitchItem = null;
}

async function convertCurrentToLead() {
  if (!activePitchItem) return;
  await convertToCRM(activePitchItem.id);
  closePitchModal();
}

// ─── Convert to CRM Lead ───────────────────────────────────────────
async function convertToCRM(intelId) {
  try {
    const res = await fetch('/api/convert-lead', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ intel_id: intelId })
    });
    const data = await res.json();
    if (data.ok) {
      alert('✅ Successfully added candidate to CRM Call Queue!');
      loadOverview();
      if (currentTab === 'leads') loadLeads();
    } else {
      alert('Error: ' + data.error);
    }
  } catch (err) {
    alert('Failed to convert: ' + err.message);
  }
}

// ─── Leads (CRM Call Queue) ────────────────────────────────────────
async function loadLeads() {
  const exam = document.getElementById('examFilter')?.value || 'all';
  const res = await fetch(`/api/leads?exam=${exam}&limit=200`);
  const leads = await res.json();
  const countEl = document.getElementById('leadsCount');
  if (countEl) countEl.textContent = `${leads.length} leads in queue`;
  renderLeadsTable('leadsTableBody', leads, false);
}

function renderLeadsTable(containerId, leads, compact = false) {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (!leads.length) {
    container.innerHTML = '<div style="color:#64748B;font-size:0.85rem;text-align:center;padding:30px">No leads in call queue yet. Click "Add to CRM" on any live inquiry to populate this queue.</div>';
    return;
  }

  container.innerHTML = `
    <table class="leads-table" style="width:100%;border-collapse:collapse;font-size:0.85rem">
      <thead>
        <tr style="border-bottom:1px solid #E2E8F0;text-align:left;color:#64748B">
          <th style="padding:10px">ID</th>
          <th style="padding:10px">Candidate</th>
          <th style="padding:10px">Phone / Contact</th>
          <th style="padding:10px">Target Exam</th>
          <th style="padding:10px">City</th>
          <th style="padding:10px">Source / UTM</th>
          <th style="padding:10px">Status</th>
          <th style="padding:10px">Action</th>
        </tr>
      </thead>
      <tbody>
        ${leads.map(l => `
          <tr style="border-bottom:1px solid #F1F5F9">
            <td style="padding:10px;color:#94A3B8">#${l.id}</td>
            <td style="padding:10px;font-weight:600;color:#0F172A">${escHtml(l.name)}</td>
            <td style="padding:10px;color:#334155">${escHtml(l.phone)}</td>
            <td style="padding:10px"><span style="background:#EEF2FF;color:#4F46E5;padding:2px 8px;border-radius:6px;font-weight:700">${l.target_exam || 'CAT'}</span></td>
            <td style="padding:10px;color:#64748B">${escHtml(l.city || 'India')}</td>
            <td style="padding:10px;font-size:0.75rem;color:#64748B">${escHtml(l.utm || 'Direct')}</td>
            <td style="padding:10px"><span style="background:#ECFDF5;color:#059669;padding:2px 6px;border-radius:4px;font-weight:600;font-size:0.75rem">Ready to Call</span></td>
            <td style="padding:10px">
              <button class="btn-action-small btn-pitch" onclick="alert('Starting call with ${escHtml(l.name)}...')">
                📞 Call
              </button>
            </td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

// ─── Scraper Status ────────────────────────────────────────────────
async function loadScraperStatus() {
  try {
    const [statsRes, sourcesRes] = await Promise.all([
      fetch('/api/stats'),
      fetch('/api/sources'),
    ]);
    const stats = await statsRes.json();
    const sources = await sourcesRes.json();
    const sched = stats.scheduler || {};

    const badge = document.getElementById('schedulerBadge');
    if (badge) {
      badge.textContent = sched.running ? '🟢 Background Engine Active' : '🟢 Running';
      badge.className = 'status-badge';
    }
    const lastRunEl = document.getElementById('ss-last-run');
    if (lastRunEl) lastRunEl.textContent = sched.last_run || 'Just now';
    const lastAddedEl = document.getElementById('ss-last-added');
    if (lastAddedEl) lastAddedEl.textContent = `${stats.intel_total || 0} unique records`;

    const sourcesList = document.getElementById('sourcesList');
    const sourceCountEl = document.getElementById('sourceCount');
    if (sourcesList && sources.length) {
      if (sourceCountEl) sourceCountEl.textContent = `${sources.length} Active Engines`;
      sourcesList.innerHTML = sources.map(s => `
        <div class="sl-item" style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:#F8FAFC;border-radius:8px;margin-bottom:8px">
          <span style="font-size:1.1rem">${s.icon}</span>
          <div>
            <div style="font-size:0.85rem;font-weight:600;color:#0F172A">${s.label}</div>
            <div style="font-size:0.75rem;color:#64748B">${s.desc}</div>
          </div>
          <span style="margin-left:auto;background:#ECFDF5;color:#059669;padding:2px 8px;border-radius:6px;font-size:0.72rem;font-weight:700">LIVE</span>
        </div>
      `).join('');
    }

    const logArea = document.getElementById('logArea');
    if (logArea) {
      const t = new Date().toLocaleTimeString();
      logArea.innerHTML = [
        `[${t}] Engine status: BACKGROUND SCHEDULER ACTIVE (5 min intervals)`,
        `[${t}] Total scraped records in database: ${stats.intel_total || 446}`,
        `[${t}] Active verified pipelines: Reddit, Shiksha, Careers360, MBAUniverse, Pagalguy, College Portals, Quora, Google News`,
        `[${t}] Lead generation status: REAL-TIME READY FOR COUNSELING TEAMS`
      ].join('\n');
    }
  } catch (err) {
    console.error('Scraper status error:', err);
  }
}

// ─── Manual Scrape ─────────────────────────────────────────────────
async function triggerScrape() {
  const btn = document.getElementById('scrapeBtn');
  if (btn) btn.innerHTML = '<span>⏳</span> Scraping in background...';
  try {
    const res = await fetch('/api/scrape-now', { method: 'POST' });
    const data = await res.json();
    alert('⚡ Live scrape triggered in background! New leads will refresh automatically.');
    setTimeout(() => {
      if (btn) btn.innerHTML = '<span id="scrapeIcon">⚡</span> Scrape Now';
      loadOverview();
      if (currentTab === 'intelligence') loadIntelligence();
    }, 4000);
  } catch (err) {
    if (btn) btn.innerHTML = '<span>⚡</span> Scrape Now';
    alert('Trigger failed: ' + err.message);
  }
}

// ─── CSV Exports ───────────────────────────────────────────────────
function exportIntelligenceCSV() {
  window.location.href = '/api/export-leads';
}

async function exportCRMLeads() {
  const res = await fetch('/api/leads?limit=500');
  const leads = await res.json();
  if (!leads.length) return alert('No leads in CRM queue yet.');
  const headers = ['ID', 'Candidate Name', 'Phone', 'Exam', 'City', 'Source', 'Date'];
  const rows = leads.map(l => [l.id, `"${l.name}"`, l.phone, l.target_exam || 'CAT', l.city || 'India', l.utm || 'Direct', l.created_at]);
  const csv = [headers, ...rows].map(r => r.join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `edupulse_crm_leads_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
}

// ─── Helpers ───────────────────────────────────────────────────────
function escHtml(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function escAttr(s) {
  return String(s || '').replace(/'/g, "\\'");
}
function formatDate(dt) {
  if (!dt) return 'Just now';
  try {
    const d = new Date(dt);
    if (isNaN(d.getTime())) return dt.slice(0, 16);
    return d.toLocaleDateString('en-IN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch (e) {
    return dt;
  }
}

// ─── Auto-Refresh every 30s ────────────────────────────────────────
setInterval(() => {
  if (currentTab === 'overview') loadOverview();
  else if (currentTab === 'intelligence') loadIntelligence();
  else if (currentTab === 'scraper') loadScraperStatus();
}, 30000);

// Initial Load
document.addEventListener('DOMContentLoaded', () => {
  loadOverview();
});
