/* =========================================================
   Polling utility
   ========================================================= */
/**
 * Generic polling helper. Calls apiFetch(url) every `interval` ms.
 *   onTick(data)  — called with each response; return true to stop polling.
 *   onDone()      — called once when onTick returns true (optional, may be async).
 *   onError(err)  — called on fetch error; polling stops automatically.
 * Returns the interval ID so callers can store/cancel it externally.
 */
function pollUntilDone({ url, interval, onTick, onDone, onError }) {
  const intervalId = setInterval(async () => {
    try {
      const data = await apiFetch(url);
      const done = await onTick(data);
      if (done) {
        clearInterval(intervalId);
        if (onDone) await onDone();
      }
    } catch (err) {
      clearInterval(intervalId);
      if (onError) onError(err);
    }
  }, interval);
  return intervalId;
}

/* =========================================================
   Tooltip engine
   ========================================================= */
const TIPS = {
  statCommits:   "Total number of commits in this repository's full history.",
  statHotspots:  "Files changed most frequently. A 'hotspot' is a file touched by many commits — high count may indicate complexity, instability, or active development.",
  statPatterns:  "Recurring engineering behaviors detected across commits: refactoring waves, revert signals, dependency migrations, and architectural shifts.",
  statCaseStudy: "An AI-generated narrative summarizing this repository's engineering history, key decisions, and observable patterns.",
  shCommits:     "Total commits extracted from this repository's full history via git clone. This includes ALL commits, not just the analyzed sample.",
  shStatusFull:      "FULLY ANALYZED — all commits have been extracted from the repository and AI-analyzed.",
  shStatusIngested:  "INGESTED — commits are extracted and stored locally. Only a sample has been AI-analyzed so far. Click + Analyze to analyze more commits.",
  shStatusIngesting: "INGESTING — commits are currently being extracted and stored locally. Wait until ingestion completes before running analysis.",
  shStatusFailed:    "FAILED — ingestion encountered an error. Try re-ingesting this repository.",
  shAnalyzed:    "Commits analyzed by AI so far. Only a sample is analyzed (not all commits) to keep costs manageable. Click '+ Analyze' to run more analyses on additional commits.",
  tlRevert:      "Reverts detected in this period. A revert undoes a previous commit — too many can indicate integration instability or premature merges.",
  tlHotspot:     "A file or area that was modified significantly more often than average during this period. May indicate complexity, active development, or a design bottleneck.",
  tlRefactorWave:"A concentrated burst of refactoring commits — the team paid down technical debt. Healthy if followed by a period of stability.",
  tlTestGrowth:  "The ratio of test commits to bugfix commits is growing — a positive signal indicating improving test coverage and engineering maturity.",
  tlMerge:       "Merge commits detected (commits with 2+ parent commits). These result from merging branches. A high number indicates an active branching workflow. Branch names are not stored, but merge activity is visible here.",
  dnaCommits:    "Total commits in the full repository history.",
  dnaBugfix:     "Over 30% of analyzed commits are bug fixes. May indicate accumulated technical debt, insufficient test coverage, or a mature product in maintenance mode.",
  dnaFeature:    "Over 40% of analyzed commits introduce new features — suggests an active product development phase.",
  dnaChurn:      "Files changed repeatedly across many commits. High churn can signal complexity, instability, or areas under active refactoring.",
  dnaAnalyzed:   "Number of commits analyzed by AI to extract categories, summaries, risk levels, and patterns.",
  dnaCaseStudy:  "A narrative case study has been generated for this repository — check the Case Study tab.",
  catFeature:    "Introduces new functionality or capabilities. Increases codebase scope.",
  catBugfix:     "Fixes a defect, error, or unexpected behavior in existing code.",
  catRefactor:   "Restructures code without changing external behavior — improves readability, reduces complexity, or prepares for future changes.",
  catDocs:       "Updates documentation, README files, comments, or code specifications. No behavior changes.",
  catTest:       "Adds, modifies, or removes automated tests. No production behavior changes.",
  catBuild:      "Changes to the build system, CI/CD pipeline, dependencies, or tooling configuration.",
  catChore:      "Routine maintenance: version bumps, cleanup, formatting, configuration. No feature or behavior changes.",
  catSecurity:   "Addresses a security vulnerability, hardens access controls, or improves authentication and authorization.",
  catUnknown:    "AI could not confidently classify this commit into a known category.",
  riskLow:       "Low risk — the change is small, well-scoped, and unlikely to introduce regressions.",
  riskMedium:    "Medium risk — the change touches multiple areas or has moderate complexity. Review carefully.",
  riskHigh:      "High risk — the change is large, touches core systems, or could introduce significant regressions. Requires thorough review.",
  thChurn:       "Total lines inserted + deleted across all commits touching this file. High churn = a lot of modification activity, often signaling complexity or instability.",
  thConfidence:  "Statistical confidence (0–100%) that this file is a true hotspot, based on its change frequency relative to the repository baseline.",
  thPeriod:      "Date range from the first to the last commit that touched this file.",
  thCommitCount: "Number of commits that modified this file.",
  sigRefactor:   "A cluster of refactoring commits concentrated in time — the team paid down technical debt in a focused burst. Healthy if followed by stability.",
  sigRevert:     "Commit reverts detected — signals unstable periods, integration conflicts, or changes that needed to be rolled back.",
  sigRevertNone: "No reverts detected in the analyzed commits — a positive signal indicating stable development with few rollbacks.",
  sigTest:       "Tests are growing faster than bug fixes — a positive quality signal suggesting improving test coverage over time.",
  sigBugfixRec:  "The same files or areas are repeatedly fixed across multiple commits. Suggests deeper design issues that partial fixes haven't resolved.",
  secHotspots:   "Files with disproportionately high change frequency. Hotspots reveal complexity bottlenecks or areas that may need architectural attention.",
  secMigrations: "Commits that replaced one library or tool with another. Reveals technology evolution and decision-making patterns over time.",
  secInsights:   "AI-generated educational explanations of detected patterns and what they mean for engineering quality.",
  migConf:       "Statistical confidence that these commits represent a genuine dependency migration rather than incidental co-occurrence.",
};

const _tipEl = document.getElementById('global-tip');
let _tipTarget = null;
function _showTip(el) {
  const key = el.dataset.tip;
  if (!key) return;
  const text = TIPS[key] || key;
  _tipEl.textContent = text;
  _tipEl.style.display = 'block';
  const r = el.getBoundingClientRect();
  let top = r.bottom + 8;
  let left = r.left;
  if (left + 290 > window.innerWidth) left = Math.max(8, window.innerWidth - 298);
  if (top + 120 > window.innerHeight) top = r.top - _tipEl.offsetHeight - 8;
  _tipEl.style.top = top + 'px';
  _tipEl.style.left = left + 'px';
  el.setAttribute('aria-describedby', 'global-tip');
  _tipTarget = el;
}
function _hideTip() {
  _tipEl.style.display = 'none';
  if (_tipTarget) { _tipTarget.removeAttribute('aria-describedby'); _tipTarget = null; }
}
let _tipsEnabled = true;
document.addEventListener('mouseover', e => { if (!_tipsEnabled) return; const t = e.target.closest('[data-tip]'); if (t) _showTip(t); else _hideTip(); });
document.addEventListener('mouseout',  e => { if (e.target.closest('[data-tip]')) _hideTip(); });
document.addEventListener('focusin',   e => { if (!_tipsEnabled) return; const t = e.target.closest('[data-tip]'); if (t) _showTip(t); });
document.addEventListener('focusout',  e => { if (e.target.closest('[data-tip]')) _hideTip(); });

document.getElementById('btn-tips').addEventListener('click', function() {
  _tipsEnabled = !_tipsEnabled;
  _hideTip();
  this.classList.toggle('active', _tipsEnabled);
  this.setAttribute('aria-pressed', _tipsEnabled ? 'true' : 'false');
});

document.getElementById('btn-theme').addEventListener('click', function() {
  const isLight = document.documentElement.dataset.theme === 'light';
  document.documentElement.dataset.theme = isLight ? '' : 'light';
  document.getElementById('icon-moon').style.display = isLight ? '' : 'none';
  document.getElementById('icon-sun').style.display  = isLight ? 'none' : '';
  document.getElementById('theme-label').textContent = isLight ? 'Dark' : 'Light';
  this.setAttribute('aria-label', isLight ? 'Switch to light mode' : 'Switch to dark mode');
  // Rebuild charts so axis colors reflect the new theme
  if (currentRepo && detailLoaded) {
    loadOverview(currentRepo);
    _rebuildPatternsChart();
  }
});

/* =========================================================
   State
   ========================================================= */
let currentRepo = null;
let currentRepoMeta = null;
let commitsLimit = 20;
let allCommits = [];
let _evidenceShaFilter = null;
let patternsData = null;
let detailLoaded = false;
let _ingestPoll = null;
let _analyzePrefetch = null;

/* =========================================================
   Chart registry
   ========================================================= */
const _charts = {};
function destroyChart(id) {
  if (_charts[id]) { _charts[id].destroy(); delete _charts[id]; }
}

/* =========================================================
   Category config
   ========================================================= */
const CAT_COLORS = {
  FEATURE: '#3b82f6', BUGFIX: '#ef4444', REFACTOR: '#f97316',
  BUILD: '#6b7280', DOCS: '#a855f7', TEST: '#22c55e',
  SECURITY: '#dc2626', PERFORMANCE: '#06b6d4', CHORE: '#6b7280',
  UNKNOWN: '#374151', OTHER: '#64748b',
};
function catColor(cat) { return CAT_COLORS[(cat || '').toUpperCase()] || '#64748b'; }
function badgeClass(category) {
  if (!category) return 'badge-default';
  const c = category.toLowerCase();
  if (c === 'feature' || c === 'feat') return 'badge-feature';
  if (c === 'bugfix' || c === 'bug' || c === 'fix') return 'badge-bugfix';
  if (c === 'refactor') return 'badge-refactor';
  if (c === 'test') return 'badge-test';
  if (c === 'docs') return 'badge-docs';
  if (c === 'security') return 'badge-security';
  if (c === 'build' || c === 'chore' || c === 'ci') return 'badge-chore';
  if (c === 'unknown') return 'badge-unknown';
  return 'badge-default';
}
function catTipKey(category) {
  const c = (category || '').toLowerCase();
  if (c === 'feature' || c === 'feat') return 'catFeature';
  if (c === 'bugfix' || c === 'bug' || c === 'fix') return 'catBugfix';
  if (c === 'refactor') return 'catRefactor';
  if (c === 'test') return 'catTest';
  if (c === 'docs') return 'catDocs';
  if (c === 'security') return 'catSecurity';
  if (c === 'build' || c === 'chore' || c === 'ci') return 'catChore';
  return 'catUnknown';
}
function riskTipKey(level) {
  const l = (level || '').toLowerCase();
  if (l === 'high') return 'riskHigh';
  if (l === 'medium') return 'riskMedium';
  return 'riskLow';
}

// Fix 3: Smart status label helper
function _repoStatusLabel(repo) {
  if (repo.status === 'COMPLETED' && repo.analysis_count > 0 && repo.analysis_count >= repo.commit_count) {
    return { label: 'FULLY ANALYZED', cls: 'status-full' };
  }
  if (repo.status === 'COMPLETED') return { label: 'INGESTED', cls: 'status-done' };
  if (repo.status === 'INGESTING') return { label: 'INGESTING', cls: 'status-ingesting' };
  if (repo.status === 'FAILED' || (repo.status || '').startsWith('FAILED_')) return { label: 'FAILED', cls: 'status-failed' };
  return { label: repo.status || '', cls: '' };
}

/* =========================================================
   Utilities
   ========================================================= */
function fmtDate(iso) { if (!iso) return '—'; try { return iso.slice(0, 10); } catch { return iso; } }
function fmtMonthDay(iso) { if (!iso) return '—'; try { return iso.slice(5, 10).replace('-', '/'); } catch { return iso; } }
function esc(str) {
  if (!str) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function truncate(str, n) { if (!str) return ''; return str.length > n ? str.slice(0, n) + '…' : str; }
function repoShortName(url) {
  try { const p = (url || '').replace(/\.git$/, '').split('/'); return p.slice(-2).join('/'); }
  catch { return url; }
}
function spinner() {
  return '<div class="loading-spinner" role="status" aria-label="Loading…"><div class="spinner" aria-hidden="true"></div><p>Loading…</p></div>';
}
async function apiFetch(url) {
  const res = await fetch(url);
  if (!res.ok) throw { status: res.status, body: await res.text() };
  return res.json();
}
function bestGranularity(commits) {
  const months = new Set(commits.map(c => (c.committed_at || '').slice(0, 7)).filter(Boolean));
  const unique = new Set(commits.map(c => (c.committed_at || '').slice(0, 10)).filter(Boolean));
  if (unique.size <= 1) return 'hour';
  if (months.size <= 2) return 'day';
  return 'month';
}
function buildActivityData(commits) {
  const g = bestGranularity(commits);
  const map = {};
  commits.forEach(c => {
    if (!c.committed_at) return;
    let key;
    if (g === 'hour') key = c.committed_at.slice(0, 13).replace('T', ' ') + 'h';
    else if (g === 'day') key = c.committed_at.slice(0, 10);
    else key = c.committed_at.slice(0, 7);
    map[key] = (map[key] || 0) + 1;
  });
  const labels = Object.keys(map).sort();
  return { labels, data: labels.map(k => map[k]), granularity: g };
}

/* =========================================================
   Repo loading & sidebar
   ========================================================= */
let reposCache = [];
async function loadRepos() {
  let data;
  try { data = await apiFetch('/api/repos'); }
  catch {
    document.getElementById('sidebar-list').innerHTML =
      '<div class="empty-state" role="alert">Could not load repositories.</div>';
    return;
  }
  reposCache = data.repos || [];
  const sidebar = document.getElementById('sidebar-list');
  sidebar.innerHTML = '';
  reposCache.forEach(repo => {
    const short = repoShortName(repo.canonical_url);
    const item = document.createElement('div');
    item.className = 'repo-item';
    item.dataset.id = repo.repository_id;
    item.setAttribute('role', 'listitem');
    item.setAttribute('tabindex', '0');
    item.setAttribute('aria-label', `${short} — ${repo.commit_count} commits, ${repo.status}`);
    item.innerHTML = `<div class="repo-name">${esc(short)}</div><div class="repo-meta">${repo.commit_count} commits · ${repo.status}</div>`;
    const activate = () => selectRepo(repo.repository_id);
    item.addEventListener('click', activate);
    item.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(); } });
    sidebar.appendChild(item);
  });
}

/* =========================================================
   Home screen
   ========================================================= */
async function renderRepoCards() {
  const grid = document.getElementById('repo-cards-grid');
  const countEl = document.getElementById('repos-count');
  if (reposCache.length === 0) {
    grid.innerHTML = '<div class="empty-state" role="status" style="grid-column:1/-1">No repositories analyzed yet. Paste a GitHub URL above to get started.</div>';
    countEl.textContent = '';
    return;
  }
  countEl.textContent = reposCache.length;
  grid.innerHTML = '<div class="loading-spinner" style="padding:2rem;grid-column:1/-1" role="status" aria-label="Loading repositories…"><div class="spinner" aria-hidden="true"></div></div>';

  const patternResults = await Promise.allSettled(
    reposCache.map(r => apiFetch(`/api/repos/${encodeURIComponent(r.repository_id)}/patterns`))
  );

  grid.innerHTML = '';
  reposCache.forEach((repo, i) => {
    const patterns = patternResults[i].status === 'fulfilled' ? patternResults[i].value : null;
    grid.appendChild(_buildRepoCard(repo, patterns));
  });
}

const _GH_ICON_SVG = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/></svg>`;

function _buildRepoCard(repo, patterns) {
  const short = repoShortName(repo.canonical_url);
  const card = document.createElement('div');
  card.className = 'repo-card';
  card.setAttribute('tabindex', '0');
  card.setAttribute('role', 'listitem');
  card.setAttribute('aria-label', `${short} — ${repo.commit_count} commits, ${repo.analysis_count} analyzed, status: ${repo.status}`);

  const signals = [];
  if (patterns?.refactor_wave)
    signals.push(`<span class="dna-pill orange" style="font-size:11px;padding:.2rem .55rem" data-tip="sigRefactor">⚡ Refactor Wave</span>`);
  if ((patterns?.revert_signal?.commit_count || 0) > 0)
    signals.push(`<span class="dna-pill red" style="font-size:11px;padding:.2rem .55rem" data-tip="sigRevert">↩️ Reverts</span>`);
  if (patterns?.test_growth_signal)
    signals.push(`<span class="dna-pill green" style="font-size:11px;padding:.2rem .55rem" data-tip="sigTest">🧪 Test Growth</span>`);
  const hotCount = (patterns?.hotspots || []).filter(h => (h.confidence || 0) >= 0.7).length;
  if (hotCount > 0)
    signals.push(`<span class="dna-pill blue" style="font-size:11px;padding:.2rem .55rem" data-tip="tlHotspot">🔥 ${hotCount} hotspot${hotCount !== 1 ? 's' : ''}</span>`);

  const { label: statusLabel, cls: statusCls } = _repoStatusLabel(repo);
  const ghUrl = repo.canonical_url && repo.canonical_url.includes('github.com') ? repo.canonical_url : null;
  card.innerHTML = `
    <div class="rc-accent" aria-hidden="true"></div>
    <div class="rc-name">${esc(short)}</div>
    <div class="rc-url">${esc(repo.canonical_url)}</div>
    <div class="rc-stats">
      <span class="rc-stat"><strong>${repo.commit_count}</strong> commits</span>
      <span class="rc-stat"><strong>${repo.analysis_count}</strong> analyzed</span>
      ${repo.has_case_study ? '<span style="color:var(--green);font-size:12px">✓ Case study</span>' : ''}
    </div>
    <div class="rc-patterns">${signals.join('')}</div>
    <div class="rc-footer">
      <span class="rc-status ${statusCls}" aria-label="Status: ${esc(statusLabel)}">${esc(statusLabel)}</span>
      <div style="display:flex;align-items:center;gap:0.5rem">
        ${ghUrl ? `<a href="${esc(ghUrl)}" target="_blank" rel="noopener" class="rc-gh-link" aria-label="View ${esc(short)} on GitHub" title="View on GitHub" onclick="event.stopPropagation()">${_GH_ICON_SVG}</a>` : ''}
        <button class="rc-open-btn" tabindex="-1" aria-hidden="true">Open timeline →</button>
      </div>
    </div>`;

  const open = () => selectRepo(repo.repository_id);
  card.addEventListener('click', open);
  card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
  return card;
}

/* =========================================================
   Add repo / ingest
   ========================================================= */
function handleAddRepo() {
  const input = document.getElementById('home-repo-input');
  const raw = input.value.trim();
  if (!raw) return;

  const statusEl = document.getElementById('ingest-status');
  const resultsEl = document.getElementById('search-results');
  resultsEl.style.display = 'none';
  resultsEl.innerHTML = '';

  let url = raw;
  if (!url.startsWith('http')) {
    if (/^[\w.\-]+\/[\w.\-]+$/.test(raw)) {
      url = `https://github.com/${raw}`;
    } else {
      const matches = reposCache.filter(r =>
        r.canonical_url.toLowerCase().includes(raw.toLowerCase()) ||
        repoShortName(r.canonical_url).toLowerCase().includes(raw.toLowerCase())
      );
      if (matches.length === 1) {
        selectRepo(matches[0].repository_id);
        return;
      } else if (matches.length > 1) {
        resultsEl.style.display = 'block';
        resultsEl.innerHTML = matches.map(r =>
          `<div class="sr-item" role="option" tabindex="0"
            onclick="selectRepo('${esc(r.repository_id)}')"
            onkeydown="if(event.key==='Enter')selectRepo('${esc(r.repository_id)}')">
            <span>${esc(repoShortName(r.canonical_url))}</span>
            <span style="font-size:11px;color:var(--muted)">${r.commit_count} commits</span>
          </div>`
        ).join('');
        statusEl.textContent = `${matches.length} matches — pick one:`;
        statusEl.style.color = 'var(--muted)';
        return;
      } else {
        statusEl.innerHTML = '';
        statusEl.textContent = 'Not found locally. Try the full GitHub URL or "owner/repo" format.';
        statusEl.style.color = 'var(--red)';
        return;
      }
    }
  }
  startIngest(url);
}

async function startIngest(url) {
  const statusEl = document.getElementById('ingest-status');
  const btn = document.getElementById('ingest-btn');
  // Set loading state
  if (btn) { btn.setAttribute('aria-busy', 'true'); btn.disabled = true; }
  statusEl.innerHTML = '<span class="ingest-spinner" aria-hidden="true"></span><span>Starting ingestion…</span>';
  statusEl.style.color = 'var(--yellow)';
  try {
    const res = await fetch('/api/repos/ingest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    if (!res.ok) {
      let msg = 'Invalid repository URL.';
      try { const e = await res.json(); msg = e.detail || msg; } catch {}
      statusEl.innerHTML = '';
      statusEl.textContent = msg;
      statusEl.style.color = 'var(--red)';
      if (btn) { btn.setAttribute('aria-busy', 'false'); btn.disabled = false; }
      return;
    }
    const data = await res.json();
    statusEl.innerHTML = `<span class="ingest-spinner" aria-hidden="true"></span><span>Ingesting ${esc(data.canonical_url)} — this may take a few minutes…</span>`;
    statusEl.style.color = 'var(--yellow)';
    _pollForRepo(data.canonical_url);
  } catch {
    statusEl.innerHTML = '';
    statusEl.textContent = 'Failed to connect to server.';
    statusEl.style.color = 'var(--red)';
    if (btn) { btn.setAttribute('aria-busy', 'false'); btn.disabled = false; }
  }
}

function _pollForRepo(canonicalUrl) {
  if (_ingestPoll) clearInterval(_ingestPoll);
  _ingestPoll = pollUntilDone({
    url: '/api/repos',
    interval: 3000,
    onTick: async (data) => {
      const found = (data.repos || []).find(r => r.canonical_url === canonicalUrl);
      if (!found) return false;
      _ingestPoll = null;
      reposCache = data.repos;
      await loadRepos();
      const statusEl = document.getElementById('ingest-status');
      const btn = document.getElementById('ingest-btn');
      statusEl.innerHTML = '';
      statusEl.textContent = `✓ ${repoShortName(canonicalUrl)} ingested!`;
      statusEl.style.color = 'var(--green)';
      if (btn) { btn.setAttribute('aria-busy', 'false'); btn.disabled = false; }
      renderRepoCards();
      setTimeout(() => selectRepo(found.repository_id), 1500);
      return true;
    },
    onError: () => {
      _ingestPoll = null;
      const btn = document.getElementById('ingest-btn');
      if (btn) { btn.setAttribute('aria-busy', 'false'); btn.disabled = false; }
    },
  });
}

/* =========================================================
   Navigation
   ========================================================= */
function goHome() {
  currentRepo = null;
  currentRepoMeta = null;
  document.getElementById('repo-view').classList.remove('visible');
  document.getElementById('home-view').style.display = '';
  document.getElementById('hdr-repo-info').style.display = 'none';
  document.getElementById('btn-tips').style.display = 'none';
  document.querySelectorAll('.repo-item').forEach(el => el.classList.remove('active'));
  renderRepoCards();
}

function selectRepo(repoId) {
  if (currentRepo === repoId && document.getElementById('repo-view').classList.contains('visible')) return;
  currentRepo = repoId;
  commitsLimit = 20;
  allCommits = [];
  patternsData = null;
  detailLoaded = false;
  _analyzePrefetch = null;
  currentRepoMeta = reposCache.find(r => r.repository_id === repoId) || null;

  document.querySelectorAll('.repo-item').forEach(el =>
    el.classList.toggle('active', el.dataset.id === repoId)
  );
  document.getElementById('home-view').style.display = 'none';
  document.getElementById('repo-view').classList.add('visible');
  document.getElementById('btn-tips').style.display = '';

  const info = document.getElementById('hdr-repo-info');
  info.style.display = 'flex';
  if (currentRepoMeta) {
    document.getElementById('hdr-repo-name').textContent = repoShortName(currentRepoMeta.canonical_url);
    document.getElementById('hdr-gh-link').href = currentRepoMeta.canonical_url;
    document.getElementById('hdr-gh-text').textContent = repoShortName(currentRepoMeta.canonical_url);
    document.getElementById('sh-commits').textContent = currentRepoMeta.commit_count + ' commits';
    const { label: shStatusLabel, cls: shStatusCls } = _repoStatusLabel(currentRepoMeta);
    const shStatusEl = document.getElementById('sh-status');
    shStatusEl.textContent = shStatusLabel;
    shStatusEl.className = 'hdr-status ' + shStatusCls;
    const _statusTipKey = { 'FULLY ANALYZED': 'shStatusFull', 'INGESTED': 'shStatusIngested', 'INGESTING': 'shStatusIngesting', 'FAILED': 'shStatusFailed' };
    shStatusEl.dataset.tip = _statusTipKey[shStatusLabel] || 'shStatusIngested';
    const analyzed = document.getElementById('sh-analyzed');
    analyzed.textContent = currentRepoMeta.analysis_count + ' analyzed';
    _loadAnalyzeEstimate(currentRepo, currentRepoMeta);
  }

async function _loadAnalyzeEstimate(repoId, meta) {
  try {
    const est = await apiFetch(`/api/repos/${encodeURIComponent(repoId)}/analyze/estimate?limit=9999`);
    _analyzePrefetch = est;
    const unanalyzed = est.unanalyzed_commits;
    const btn = document.getElementById('sh-analyze-btn');
    if (unanalyzed > 0 && btn) {
      const cost = est.estimated_cost_usd > 0 ? ` (~$${est.estimated_cost_usd.toFixed(4)} total)` : '';
      btn.title = `${unanalyzed} of ${est.total_commits} commits not yet analyzed${cost}`;
      btn.setAttribute('data-tip-override', `${unanalyzed} unanalyzed commits. Click to analyze${cost}.`);
    }
  } catch { /* non-critical */ }
}

  switchView('timeline');
  loadTimeline(repoId);
}

/* =========================================================
   View switching
   ========================================================= */
function switchView(view) {
  const isTimeline = view === 'timeline';
  document.getElementById('panel-timeline').style.display = isTimeline ? 'block' : 'none';
  document.getElementById('panel-detail').style.display = isTimeline ? 'none' : 'flex';
  document.getElementById('view-btn-timeline').classList.toggle('active', isTimeline);
  document.getElementById('view-btn-detail').classList.toggle('active', !isTimeline);
  document.getElementById('view-btn-timeline').setAttribute('aria-selected', isTimeline ? 'true' : 'false');
  document.getElementById('view-btn-detail').setAttribute('aria-selected', isTimeline ? 'false' : 'true');

  if (!isTimeline && !detailLoaded && currentRepo) {
    detailLoaded = true;
    switchTab('overview');
    loadOverview(currentRepo);
    loadCaseStudy(currentRepo);
    loadPatterns(currentRepo);
    loadCommits(currentRepo, false);
    loadContributors(currentRepo);
  }
}

document.getElementById('view-btn-timeline').addEventListener('click', () => { switchView('timeline'); if (currentRepo) loadTimeline(currentRepo); });
document.getElementById('view-btn-detail').addEventListener('click', () => switchView('detail'));

/* =========================================================
   Timeline
   ========================================================= */
let _tlAllCommits = [];
let _tlPatterns = null;

async function _applyTimelineFilters() {
  if (!currentRepo) return;
  const limit = document.getElementById('tl-limit-select')?.value || '200';
  const limitN = parseInt(limit);
  const keyword = (document.getElementById('tl-search')?.value || '').toLowerCase().trim();
  const fromDate = document.getElementById('tl-date-from')?.value;
  const toDate = document.getElementById('tl-date-to')?.value;
  if (limitN > _tlAllCommits.length) {
    await loadTimeline(currentRepo);
    return;
  }
  // Always apply the limit — fixes going from large → small limit
  let commits = _tlAllCommits.slice(0, limitN);
  // Fix 4: Apply date range filter
  if (fromDate) commits = commits.filter(c => (c.committed_at || '') >= fromDate);
  if (toDate) commits = commits.filter(c => (c.committed_at || '') <= toDate + 'T23:59:59');
  if (keyword) {
    commits = commits.filter(c =>
      (c.message||'').toLowerCase().includes(keyword) ||
      (c.author_name||'').toLowerCase().includes(keyword) ||
      (c.sha||'').toLowerCase().startsWith(keyword) ||
      (c.category||'').toLowerCase().includes(keyword) ||
      (c.summary||'').toLowerCase().includes(keyword)
    );
  }
  renderTimeline(commits, _tlPatterns);
}

async function loadTimeline(repoId) {
  const el = document.getElementById('timeline-content');
  el.innerHTML = spinner();
  try {
    const [commitsData, patterns] = await Promise.all([
      apiFetch(`/api/repos/${encodeURIComponent(repoId)}/commits?order=oldest&limit=1000`),
      apiFetch(`/api/repos/${encodeURIComponent(repoId)}/patterns`),
    ]);
    _tlAllCommits = commitsData.commits || [];
    _tlPatterns = patterns;
    // Build limit selector options based on actual count
    const sel = document.getElementById('tl-limit-select');
    if (sel) {
      const n = _tlAllCommits.length;
      const steps = [10, 20, 50, 100, 200, 500].filter(s => s <= n);
      if (!steps.includes(n)) steps.push(n);
      sel.innerHTML = steps.map(s => `<option value="${s}"${s === n ? ' selected' : ''}>${s === n ? `All (${n})` : s + ' commits'}</option>`).join('');
    }
    renderTimeline(_tlAllCommits, patterns);
  } catch {
    el.innerHTML = '<div class="tl-empty">Error loading timeline data.</div>';
  }
}

function buildSignalIndex(patterns) {
  const idx = {};
  function add(isoDate, sig) {
    if (!isoDate) return;
    const m = isoDate.slice(0, 7);
    if (!idx[m]) idx[m] = [];
    idx[m].push(sig);
  }
  if (patterns?.refactor_wave?.time_range?.[0])
    add(patterns.refactor_wave.time_range[0], { icon: '🔁', label: 'Refactor Wave', desc: `${patterns.refactor_wave.commit_count || 0} refactor commits · ${((patterns.refactor_wave.ratio || 0) * 100).toFixed(0)}% of analyzed` });
  const revertCount = patterns?.revert_signal?.commit_count || 0;
  if (revertCount > 0 && patterns.revert_signal.time_range?.[0])
    add(patterns.revert_signal.time_range[0], { icon: '↩️', label: 'Revert Signal', desc: `${revertCount} reverts detected` });
  if (patterns?.test_growth_signal?.time_range?.[0])
    add(patterns.test_growth_signal.time_range[0], { icon: '🧪', label: 'Test Growth', desc: `test:bug ratio ${(patterns.test_growth_signal.ratio || 0).toFixed(2)}` });
  (patterns?.hotspots || []).filter(h => (h.confidence || 0) >= 0.7).slice(0, 3).forEach(h => {
    if (h.time_range?.[0]) {
      const file = (h.file_path || '').split('/').pop();
      add(h.time_range[0], { icon: '🔥', label: `Hotspot: ${file}`, desc: `${h.commit_count} commits · ${((h.confidence || 0) * 100).toFixed(0)}% confidence` });
    }
  });
  return idx;
}

function renderTimeline(commits, patterns) {
  const el = document.getElementById('timeline-content');
  if (!commits.length) {
    el.innerHTML = `<div class="tl-empty">
      <p>No analyzed commits yet.</p>
      <p style="margin-top:.5rem">Use the <strong>+ Analyze</strong> button above to start commit analysis.</p>
    </div>`;
    return;
  }

  const allDates = commits.map(c => c.committed_at).filter(Boolean).sort();
  const firstDate = allDates[0] ? allDates[0].slice(0, 10) : null;
  const lastDate = allDates[allDates.length - 1] ? allDates[allDates.length - 1].slice(0, 10) : null;


  const monthMap = {};
  commits.forEach(c => {
    const m = (c.committed_at || '').slice(0, 7);
    if (!monthMap[m]) monthMap[m] = [];
    monthMap[m].push(c);
  });

  let html = '';
  if (firstDate && lastDate) {
    const mergeCommits = commits.filter(c => { try { return JSON.parse(c.parent_shas || '[]').length > 1; } catch { return false; } }).length;
    html += `<div class="tl-timeframe" aria-label="Analysis time range">
      Commits from <strong>${firstDate}</strong> to <strong>${lastDate}</strong>
      <span style="color:var(--border)">·</span> <strong>${commits.length}</strong> shown
      ${mergeCommits > 0 ? `<span style="color:var(--border)">·</span> <span data-tip="tlMerge" tabindex="0" style="color:var(--muted)">↔ ${mergeCommits} merge${mergeCommits !== 1 ? 's' : ''}</span>` : ''}
    </div>`;
  }
  html += '<div class="timeline">';

  Object.keys(monthMap).sort().forEach(month => {
    const monthCommits = monthMap[month];
    const [yr, mo] = month.split('-');
    const label = new Date(parseInt(yr), parseInt(mo) - 1, 1)
      .toLocaleDateString('en-US', { month: 'long', year: 'numeric' });

    html += `<div class="tl-month" data-month="${month}" id="tl-month-${month.replace('-','')}">
      <div class="tl-month-hdr"><span>${esc(label)}</span><div class="tl-month-line"></div></div>`;

    html += '<div class="tl-commits-group">';
    monthCommits.forEach((c, i) => {
      const xid = `tlx-${month.replace('-', '')}-${i}`;
      const cat = (c.category || '').toUpperCase();
      const hasAnalysis = !!(c.category || c.summary);
      const isHigh = (c.importance || '').toLowerCase() === 'high';
      html += `<div class="tl-row${hasAnalysis ? ' analyzed' : ''}${isHigh ? ' risk-high' : ''}"
               id="tlr-${xid}" onclick="tlToggle('${xid}')"
               role="button" tabindex="0" aria-expanded="false"
               onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();tlToggle('${xid}')}">
        <span class="tl-date">${esc(fmtMonthDay(c.committed_at || ''))}</span>
        <span class="tl-msg">${esc(truncate(c.message || '', isHigh ? 60 : 70))}</span>
        <div class="tl-badges">
          ${cat ? `<span class="badge ${badgeClass(c.category || '')}" data-tip="${catTipKey(c.category || '')}">${esc(cat)}</span>` : ''}
          ${isHigh ? '<span class="badge badge-risk-high" aria-label="High risk">HIGH RISK</span>' : ''}
        </div>
      </div>`;
      if (c.summary && c.summary !== c.message) {
        html += `<div class="tl-detail" id="${xid}">
          ${esc(c.summary)}
          <span style="margin-left:.5rem;font-family:monospace;font-size:10px;color:var(--muted)">${esc((c.sha || '').slice(0, 7))}</span>
        </div>`;
      }
    });
    html += '</div></div>';
  });
  html += '</div>';
  el.innerHTML = html;
}

function tlToggle(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle('open');
  const row = document.getElementById('tlr-' + id);
  if (row) row.setAttribute('aria-expanded', el.classList.contains('open') ? 'true' : 'false');
}

/* =========================================================
   Deep Analysis tabs
   ========================================================= */
function switchTab(tabName) {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.setAttribute('aria-selected', btn.dataset.tab === tabName ? 'true' : 'false');
  });
  document.querySelectorAll('.tab-panel').forEach(panel =>
    panel.classList.toggle('active', panel.id === 'tab-' + tabName)
  );
}
document.querySelectorAll('.tab-btn').forEach(btn =>
  btn.addEventListener('click', () => {
    if (btn.dataset.tab === 'commits') _clearCommitFilters();
    switchTab(btn.dataset.tab);
  })
);

/* =========================================================
   Overview
   ========================================================= */
async function loadOverview(repoId) {
  const el = document.getElementById('overview-content');
  el.innerHTML = spinner();

  let patterns, commits, caseStudy;
  try {
    [patterns, commits] = await Promise.all([
      apiFetch(`/api/repos/${encodeURIComponent(repoId)}/patterns`),
      apiFetch(`/api/repos/${encodeURIComponent(repoId)}/commits?limit=500&order=newest`),
    ]);
    try { caseStudy = await apiFetch(`/api/repos/${encodeURIComponent(repoId)}/case-study`); }
    catch { caseStudy = null; }
  } catch {
    el.innerHTML = '<div class="empty-state" role="alert">Error loading overview data.</div>';
    return;
  }

  const totalCommits = commits.total || (commits.commits || []).length;
  const hotspots = (patterns.hotspots || []).filter(h => (h.confidence || 0) >= 0.7);
  const hotspotCount = hotspots.length;
  const patternCount = [patterns.refactor_wave, patterns.revert_signal, patterns.test_growth_signal, ...(patterns.dependency_migrations || [])].filter(Boolean).length;
  const catCounts = patterns.category_counts || [];
  const totalCat = catCounts.reduce((s, c) => s + c.count, 0);
  const bugfixCount = (catCounts.find(c => c.category.toLowerCase() === 'bugfix') || {}).count || 0;
  const featureCount = (catCounts.find(c => c.category.toLowerCase() === 'feature') || {}).count || 0;

  const pills = [];
  pills.push(`<span class="dna-pill blue" data-tip="dnaCommits">⚡ ${totalCommits} commits</span>`);
  if (totalCat > 0 && bugfixCount / totalCat > 0.30) pills.push(`<span class="dna-pill red" data-tip="dnaBugfix">🐛 High bug-fix rate</span>`);
  if (totalCat > 0 && featureCount / totalCat > 0.40) pills.push(`<span class="dna-pill blue" data-tip="dnaFeature">🚀 Feature-heavy</span>`);
  if (hotspotCount > 0) pills.push(`<span class="dna-pill orange" data-tip="dnaChurn">🔥 ${hotspotCount} hotspot files</span>`);
  if (currentRepoMeta && currentRepoMeta.analysis_count > 0) pills.push(`<span class="dna-pill purple" data-tip="dnaAnalyzed">📦 ${currentRepoMeta.analysis_count} analyzed</span>`);
  if (caseStudy) pills.push(`<span class="dna-pill green" data-tip="dnaCaseStudy">✅ Case study ready</span>`);

  el.innerHTML = `
    <div class="charts-row">
      <div class="chart-box">
        <h3>Commit Categories</h3>
        <div class="chart-container" style="height:170px"><canvas id="chart-donut" aria-label="Donut chart showing commit category distribution"></canvas></div>
        <div id="donut-legend-custom" class="donut-legend" role="list" aria-label="Category legend"></div>
      </div>
      <div class="chart-box">
        <h3>Commit Activity</h3>
        <div class="chart-container" style="height:220px"><canvas id="chart-activity" aria-label="Bar chart showing commit activity over time"></canvas></div>
      </div>
    </div>
    <div class="chart-box" style="margin-bottom:1rem">
      <h3>Top Hotspot Files <span style="font-size:10px;font-weight:400;color:var(--muted);text-transform:none">(click to filter commits)</span></h3>
      <div class="chart-container" style="height:${Math.max(120, Math.min(hotspots.slice(0,5).length, 5) * 36)}px">
        <canvas id="chart-hotspots" aria-label="Horizontal bar chart showing top hotspot files by commit count"></canvas>
      </div>
    </div>`;

  const _tc = () => document.documentElement.dataset.theme === 'light' ? '#475569' : '#94a3b8';
  const _tcy = () => document.documentElement.dataset.theme === 'light' ? '#0f172a' : '#e2e8f0';
  const _gc = () => document.documentElement.dataset.theme === 'light' ? '#e2e8f0' : '#2d3148';

  if (catCounts.length > 0) {
    destroyChart('donut');
    _charts['donut'] = new Chart(document.getElementById('chart-donut'), {
      type: 'doughnut',
      data: { labels: catCounts.map(c => c.category), datasets: [{ data: catCounts.map(c => c.count), backgroundColor: catCounts.map(c => catColor(c.category)), borderWidth: 1, borderColor: '#0f1117' }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        onClick(evt, els) {
          if (!els.length) return;
          const cat = catCounts[els[0].index]?.category;
          if (!cat) return;
          switchView('detail'); switchTab('commits');
          const sel = document.getElementById('cat-filter');
          if (sel) { sel.value = cat.toUpperCase(); _applyCommitFilter(`Category: ${cat}`); }
        },
      },
    });
    const legendEl = document.getElementById('donut-legend-custom');
    if (legendEl) legendEl.innerHTML = catCounts.map(c =>
      `<span class="donut-legend-item" data-tip="${catTipKey(c.category)}" tabindex="0" role="listitem">
        <span class="donut-legend-dot" style="background:${catColor(c.category)}" aria-hidden="true"></span>
        ${esc(c.category.toLowerCase())}
      </span>`
    ).join('');
  } else {
    document.getElementById('chart-donut').parentElement.innerHTML = '<div class="empty-state" style="padding:1rem">No category data</div>';
  }

  const commitList = commits.commits || [];
  const { labels: actLabels, data: actData } = buildActivityData(commitList);
  if (actLabels.length > 0) {
    destroyChart('activity');
    _charts['activity'] = new Chart(document.getElementById('chart-activity'), {
      type: 'bar',
      data: { labels: actLabels, datasets: [{ label: 'Commits', data: actData, backgroundColor: '#6366f1', borderRadius: 3 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { footer: () => 'Click to view in Timeline' } } },
        scales: { x: { ticks: { color: _tc(), font: { size: 10 }, maxRotation: 45 }, grid: { color: _gc() } }, y: { ticks: { color: _tc(), font: { size: 10 } }, grid: { color: _gc() } } },
        onClick(evt, els) {
          if (!els.length) return;
          const period = actLabels[els[0].index];
          if (!period) return;
          switchView('timeline');
          setTimeout(() => {
            let fromDate, toDate;
            if (period.length === 7) {
              const [y, m] = period.split('-').map(Number);
              fromDate = `${period}-01`;
              toDate = new Date(y, m, 0).toISOString().slice(0, 10);
            } else {
              const day = period.slice(0, 10);
              fromDate = day;
              toDate = day;
            }
            const fromEl = document.getElementById('tl-date-from');
            const toEl = document.getElementById('tl-date-to');
            if (fromEl) fromEl.value = fromDate;
            if (toEl) toEl.value = toDate;
            _applyTimelineFilters();
          }, 300);
        },
      },
    });
  }

  const top5 = hotspots.slice(0, 5);
  if (top5.length > 0) {
    destroyChart('hotspots');
    _charts['hotspots'] = new Chart(document.getElementById('chart-hotspots'), {
      type: 'bar',
      data: { labels: top5.map(h => h.file_path.split('/').pop()), datasets: [{ label: 'Commits', data: top5.map(h => h.commit_count), backgroundColor: top5.map(h => { const c=h.confidence||0; return c>=0.7?'#ef4444':c>=0.4?'#eab308':'#22c55e'; }), borderRadius: 3 }] },
      options: {
        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { footer: () => 'Click to view commits for this file' } } },
        scales: { x: { ticks: { color: _tc(), font: { size: 10 } }, grid: { color: _gc() } }, y: { ticks: { color: _tcy(), font: { size: 11 } }, grid: { display: false } } },
        onClick(evt, els) {
          if (!els.length) return;
          const h = top5[els[0].index];
          if (!h) return;
          const fname = h.file_path.split('/').pop();
          const shas = h.evidence_commit_shas || [];
          if (shas.length) {
            _filterByEvidenceShas(shas, `File: ${fname}`);
          } else {
            _searchCommitsByFile(h.file_path);
          }
        },
      },
    });
  } else {
    document.getElementById('chart-hotspots').parentElement.innerHTML = '<div class="empty-state" style="padding:1rem">No hotspot data</div>';
  }
}

/* =========================================================
   Case Study
   ========================================================= */
const _HEADING_ICONS = [
  [/security|auth|credential|permission|vulnerab|cve/i, '🔒'],
  [/performance|speed|latency|slow|optim|cache/i, '⚡'],
  [/test|spec|coverage|mock|assertion/i, '🧪'],
  [/bug|fix|error|exception|crash|defect|fail/i, '🐛'],
  [/revert|rollback|undo/i, '↩️'],
  [/feature|new|launch|release|introduce/i, '🚀'],
  [/refactor|cleanup|restructur|reorganiz/i, '🔁'],
  [/depend|package|librar|import|migrat|upgrade/i, '📦'],
  [/api|endpoint|route|rest|graphql|webhook/i, '🔌'],
  [/database|sql|migrat|schema|store|persist/i, '🗄️'],
  [/docker|container|kubernetes|k8s|image/i, '🐳'],
  [/ci|cd|pipeline|deploy|build|workflow/i, '🤖'],
  [/frontend|ui|css|html|style|component|design/i, '🎨'],
  [/architect|struct|pattern|design|domain/i, '🏗️'],
  [/doc|readme|comment|changelog/i, '📚'],
  [/config|env|setting|variable|secret/i, '⚙️'],
  [/mistake|wrong|correction|error|lesson|learn/i, '🎓'],
  [/transition|shift|evolv|replac/i, '🔄'],
  [/evidence|index|reference|source|commit/i, '🔍'],
  [/limitation|caveat|constraint|unknown|uncertain/i, '⚠️'],
  [/component|module|service|layer|class/i, '🧩'],
  [/timeline|histor|chronolog|period/i, '📅'],
  [/contributor|author|team|developer|collabor/i, '👥'],
  [/overview|summary|introduction|background/i, '📋'],
];

function _iconForHeading(title) {
  for (const [re, icon] of _HEADING_ICONS) {
    if (re.test(title)) return icon;
  }
  return '📄';
}

function _renderSectionCards(content) {
  const lines = (content || '').split('\n');
  const cards = [];
  let current = null;
  lines.forEach(line => {
    const m = line.match(/^###\s+(.+)$/);
    if (m) {
      if (current) cards.push(current);
      current = { title: m[1].trim(), lines: [] };
    } else if (current) {
      current.lines.push(line);
    }
  });
  if (current) cards.push(current);

  if (cards.length === 0) {
    const html = typeof marked !== 'undefined' ? marked.parse(content) : '<pre>' + esc(content) + '</pre>';
    return `<div class="markdown-body">${html}</div>`;
  }

  return cards.map((card, i) => {
    const cleanTitle = card.title.replace(/\*\*/g, '').replace(/^#+\s*/, '').trim();
    // Fix 5: Detect architectural pattern section for special styling
    const isArchPattern = /architect|key pattern|design pattern|structural pattern/i.test(cleanTitle);
    const icon = isArchPattern ? '🏛' : _iconForHeading(cleanTitle);
    const body = card.lines.join('\n').trim();
    const html = typeof marked !== 'undefined' ? marked.parse(body) : '<pre>' + esc(body) + '</pre>';
    const extraCls = isArchPattern ? ' cs-arch-pattern-card open' : '';
    return `<div class="cs-subcard${extraCls}" id="csc-${i}">
      <div class="cs-subcard-hdr" onclick="this.parentElement.classList.toggle('open')" role="button" tabindex="0"
           onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();this.parentElement.classList.toggle('open')}">
        <span class="cs-subcard-icon" aria-hidden="true">${icon}</span>
        <span class="cs-subcard-title">${esc(cleanTitle)}</span>
        <span class="cs-subcard-chevron" aria-hidden="true">▶</span>
      </div>
      <div class="cs-subcard-body">
        <div class="markdown-body">${html}</div>
      </div>
    </div>`;
  }).join('');
}

const _COLLAPSIBLE_TABS = new Set(['Main Components Through Time','Key Mistakes and Corrections','Architectural Transitions','Engineering Lessons']);
const _HIDDEN_CS_SECTIONS = new Set(['Evidence Index','Limitations']);

function _renderCsTimeline(content) {
  const lines = (content || '').split('\n');
  const phases = [];
  let current = null;
  lines.forEach(line => {
    const m = line.match(/^###\s+(.+)$/);
    if (m) {
      if (current) phases.push(current);
      current = { title: m[1].replace(/\*\*/g, '').trim(), lines: [] };
    } else if (current) {
      current.lines.push(line);
    }
  });
  if (current) phases.push(current);

  if (!phases.length) {
    return typeof marked !== 'undefined' ? `<div class="markdown-body">${marked.parse(content)}</div>` : `<pre>${esc(content)}</pre>`;
  }

  // Distribute commits equally across phases (approximation without explicit date boundaries)
  const sorted = (allCommits || []).slice().sort((a,b) => (a.committed_at||'') < (b.committed_at||'') ? -1 : 1);
  const total = sorted.length;
  const perPhase = phases.length ? Math.ceil(total / phases.length) : 0;
  const buckets = phases.map((p, idx) => {
    const slice = sorted.slice(idx * perPhase, (idx + 1) * perPhase);
    return {
      dateRange: slice.length ? `${slice[0].committed_at.slice(0,10)} → ${slice[slice.length-1].committed_at.slice(0,10)}` : '',
      count: slice.length,
    };
  });

  // Horizontal timeline rail
  let html = `<div class="cs-tl-rail" role="list" aria-label="Chronological timeline phases">`;
  phases.forEach((p, idx) => {
    const b = buckets[idx];
    const icon = _iconForHeading(p.title);
    const isLast = idx === phases.length - 1;
    html += `<div class="cs-tl-node" role="listitem" onclick="_csTlOpen(${idx})" tabindex="0"
      onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();_csTlOpen(${idx})}"
      title="Click to read: ${esc(p.title)}">
      <div class="cs-tl-dot">${icon}</div>
      ${!isLast ? '<div class="cs-tl-line" aria-hidden="true"></div>' : ''}
      <div class="cs-tl-label">
        <div class="cs-tl-label-title">${esc(p.title)}</div>
        ${b.dateRange ? `<div class="cs-tl-label-range">${esc(b.dateRange)}</div>` : ''}
        ${b.count ? `<div class="cs-tl-label-cnt">${b.count} commits</div>` : ''}
      </div>
    </div>`;
  });
  html += `</div>`;

  // Detail cards (hidden by default, opened on click)
  html += `<div id="cs-tl-cards" style="margin-top:1rem">`;
  phases.forEach((p, idx) => {
    const bodyRaw = p.lines.join('\n').trim();
    // Detect sub-sections: #### headings OR standalone bold lines (**Title** or **Title:**)
    const subSections = [];
    let currentSub = null;
    bodyRaw.split('\n').forEach(line => {
      const h4 = line.match(/^####\s+(.+)$/);
      const bold = !h4 && line.match(/^\s*\*\*([^*]{4,60})\*\*:?\s*$/);
      const m = h4 || bold;
      if (m) {
        if (currentSub) subSections.push(currentSub);
        currentSub = { title: m[1].replace(/\*\*/g,'').trim(), lines: [] };
      } else if (currentSub) {
        currentSub.lines.push(line);
      }
    });
    if (currentSub) subSections.push(currentSub);
    const md = typeof marked !== 'undefined' ? marked.parse(bodyRaw) : `<pre>${esc(bodyRaw)}</pre>`;
    const subRail = subSections.length > 1
      ? `<div class="cs-tl-sub-rail" aria-label="Sub-phases" style="margin:0.75rem 0 0.5rem">` +
        subSections.map((s, si) => {
          const isLast = si === subSections.length - 1;
          return `<div class="cs-tl-sub-node" title="${esc(s.title)}">
            <div class="cs-tl-sub-dot">${_iconForHeading(s.title)}</div>
            ${!isLast ? '<div class="cs-tl-sub-line" aria-hidden="true"></div>' : ''}
            <div class="cs-tl-sub-label">${esc(s.title.slice(0, 30))}</div>
          </div>`;
        }).join('') + `</div>`
      : '';
    html += `<div class="cs-subcard" id="cs-tl-card-${idx}">
      <div class="cs-subcard-hdr" onclick="this.parentElement.classList.toggle('open')" role="button" tabindex="0"
           onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();this.parentElement.classList.toggle('open')}">
        <span class="cs-subcard-icon" aria-hidden="true">${_iconForHeading(p.title)}</span>
        <span class="cs-subcard-title">${esc(p.title)}</span>
        <span class="cs-subcard-chevron" aria-hidden="true">▶</span>
      </div>
      <div class="cs-subcard-body">${subRail}<div class="markdown-body">${md}</div></div>
    </div>`;
  });
  html += `</div>`;
  return html;
}

function _csTlOpen(idx) {
  const card = document.getElementById(`cs-tl-card-${idx}`);
  if (!card) return;
  card.classList.add('open');
  card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function _renderArchTransition(content) {
  const cards = [];
  const lines = (content || '').split('\n');
  let current = null;
  lines.forEach(line => {
    const m = line.match(/^###\s+(.+)$/);
    if (m) {
      if (current) cards.push(current);
      current = { title: m[1].replace(/\*\*/g, '').trim(), lines: [] };
    } else if (current) {
      current.lines.push(line);
    }
  });
  if (current) cards.push(current);
  if (!cards.length) {
    return typeof marked !== 'undefined' ? `<div class="markdown-body">${marked.parse(content)}</div>` : `<pre>${esc(content)}</pre>`;
  }
  return cards.map((card, i) => {
    const body = card.lines.join('\n');
    const rest = typeof marked !== 'undefined' ? marked.parse(body) : `<pre>${esc(body)}</pre>`;
    return `<div class="cs-subcard" id="arch-${i}">
      <div class="cs-subcard-hdr" onclick="this.parentElement.classList.toggle('open')" role="button" tabindex="0"
           onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();this.parentElement.classList.toggle('open')}">
        <span class="cs-subcard-icon" aria-hidden="true">🔄</span>
        <span class="cs-subcard-title">${esc(card.title)}</span>
        <span class="cs-subcard-chevron" aria-hidden="true">▶</span>
      </div>
      <div class="cs-subcard-body"><div class="markdown-body">${rest}</div></div>
    </div>`;
  }).join('');
}

function _splitNarrative(text) {
  const sections = [];
  const lines = (text || '').split('\n');
  let current = null;
  lines.forEach(line => {
    const m = line.match(/^##\s+(.+)$/);
    if (m) {
      if (current) sections.push(current);
      current = { title: m[1].trim(), lines: [] };
    } else if (current) {
      current.lines.push(line);
    }
  });
  if (current) sections.push(current);
  return sections
    .map(s => ({ title: s.title, content: s.lines.join('\n').trim() }))
    .filter(s => !_HIDDEN_CS_SECTIONS.has(s.title));
}

function _csSwitchTab(idx) {
  document.querySelectorAll('.cs-tab-btn').forEach((b, i) => b.classList.toggle('active', i === idx));
  document.querySelectorAll('.cs-section').forEach((s, i) => s.classList.toggle('active', i === idx));
}

// Fix 6: Linkify commit SHAs in case study HTML
function _linkifyCommitShas(html, canonicalUrl) {
  if (!canonicalUrl || !canonicalUrl.includes('github.com')) return html;
  // Match 7-40 char hex strings not already inside an href attribute
  return html.replace(/(?<!href=["'][^"']{0,200})\b([0-9a-f]{7,40})\b/gi, (match, sha) => {
    const ghUrl = `${canonicalUrl}/commit/${sha}`;
    return `<a href="${ghUrl}" target="_blank" rel="noopener" title="View commit ${sha} on GitHub" style="font-family:monospace;color:var(--accent);text-decoration:none" onmouseover="this.style.textDecoration='underline'" onmouseout="this.style.textDecoration='none'">${sha}</a>`;
  });
}

async function loadCaseStudy(repoId) {
  const el = document.getElementById('case-study-content');
  el.innerHTML = spinner();
  let data;
  const _aud = localStorage.getItem('cs-audience') || 'beginner';
  try { data = await apiFetch(`/api/repos/${encodeURIComponent(repoId)}/case-study?audience=${encodeURIComponent(_aud)}`); }
  catch (e) {
    if (e.status === 404 && _aud !== 'beginner') {
      // Requested audience not generated yet — fall back to beginner
      localStorage.setItem('cs-audience', 'beginner');
      loadCaseStudy(repoId);
      return;
    }
    el.innerHTML = e.status === 404
      ? '<div class="empty-state">No case study generated yet. Run analysis first.</div>'
      : '<div class="empty-state" role="alert">Error loading case study.</div>';
    return;
  }
  const canonicalUrl = currentRepoMeta ? currentRepoMeta.canonical_url : data.repository_id;
  const sections = _splitNarrative(data.narrative || '');
  const words = (data.narrative || '').trim().split(/\s+/).length;
  const currentAudience = localStorage.getItem('cs-audience') || 'beginner';
  const chips = `<div class="meta-chips">
    <span class="chip" data-tip="statCommits" tabindex="0">${data.commit_count} commits</span>
    <span class="chip" data-tip="secHotspots" tabindex="0">${data.hotspot_count} hotspots</span>
    <span class="chip gray">${words} words</span>
    ${data.generated_at ? `<span class="chip gray">Generated ${fmtDate(data.generated_at)}</span>` : ''}
    <span class="cs-audience-wrap" title="Switch audience — cached versions load instantly; new levels generate in background (~1 min)">
      <span class="cs-audience-label">Audience:</span>
      <select class="cs-audience-select" onchange="_setCsAudience(this.value)" aria-label="Case study audience level">
        <option value="beginner"${currentAudience === 'beginner' ? ' selected' : ''}>Beginner</option>
        <option value="expert"${currentAudience === 'expert' ? ' selected' : ''}>Expert</option>
      </select>
    </span>
  </div>`;

  let tabBtns = '';
  let tabPanels = '';
  if (sections.length > 0) {
    sections.forEach((s, i) => {
      const useCards = _COLLAPSIBLE_TABS.has(s.title);
      const isArch = s.title === 'Architectural Transitions';
      const isTl = s.title === 'Timeline';
      const body = isArch ? _renderArchTransition(s.content)
        : isTl ? _renderCsTimeline(s.content)
        : (useCards ? _renderSectionCards(s.content) : (typeof marked !== 'undefined' ? `<div class="markdown-body">${marked.parse(s.content)}</div>` : `<pre>${esc(s.content)}</pre>`));
      tabBtns += `<button class="cs-tab-btn${i === 0 ? ' active' : ''}" onclick="_csSwitchTab(${i})" role="tab" aria-selected="${i === 0}" aria-controls="cs-sec-${i}" id="cs-btn-${i}">${esc(s.title)}</button>`;
      tabPanels += `<div class="cs-section${i === 0 ? ' active' : ''}" id="cs-sec-${i}" role="tabpanel" aria-labelledby="cs-btn-${i}" tabindex="0">${body}</div>`;
    });
  } else {
    const html = typeof marked !== 'undefined' ? marked.parse(data.narrative || '') : '<pre>' + esc(data.narrative || '') + '</pre>';
    tabPanels = `<div class="cs-section active"><div class="markdown-body">${html}</div></div>`;
  }

  // Fix 6: Linkify commit SHAs in the rendered panels
  const linkedTabPanels = _linkifyCommitShas(tabPanels, canonicalUrl);

  el.innerHTML = `
    <div class="case-study-header">
      <div class="case-study-title">${esc(repoShortName(canonicalUrl))}</div>
      <div class="case-study-meta"><a href="${esc(canonicalUrl)}" target="_blank" rel="noopener">${esc(canonicalUrl)} ↗</a></div>
      ${chips}
    </div>
    ${sections.length > 0 ? `<div class="cs-tabs" role="tablist" aria-label="Case study sections">${tabBtns}</div>` : ''}
    ${linkedTabPanels}`;
}

async function _setCsAudience(value) {
  localStorage.setItem('cs-audience', value);
  if (!currentRepo) return;
  const el = document.getElementById('case-study-content');
  el.innerHTML = spinner();
  // Try loading cached version for this audience first
  try {
    await apiFetch(`/api/repos/${encodeURIComponent(currentRepo)}/case-study?audience=${encodeURIComponent(value)}`);
    // Cached — just reload normally
    loadCaseStudy(currentRepo);
    return;
  } catch (e) {
    if (e.status !== 404) {
      el.innerHTML = '<div class="empty-state" role="alert">Error checking case study.</div>';
      return;
    }
  }
  // Not cached — trigger background regeneration
  el.innerHTML = `<div class="empty-state">${spinner()}<p style="color:var(--yellow);margin-top:0.5rem">Generating ${value} case study… this may take a minute.</p></div>`;
  let regenRes;
  try {
    regenRes = await fetch(`/api/repos/${encodeURIComponent(currentRepo)}/case-study/regenerate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ audience: value }),
    });
  } catch {
    el.innerHTML = '<div class="empty-state" role="alert">Failed to start regeneration — check that the server is running.</div>';
    return;
  }
  if (!regenRes.ok) {
    el.innerHTML = `<div class="empty-state" role="alert">Regeneration failed (HTTP ${regenRes.status}). Try restarting the server.</div>`;
    return;
  }
  _pollRegenStatus(currentRepo, value);
}

function _pollRegenStatus(repoId, audience) {
  const el = document.getElementById('case-study-content');
  pollUntilDone({
    url: `/api/repos/${encodeURIComponent(repoId)}/case-study/regen-status`,
    interval: 2000,
    onTick: (s) => !s.running,
    onDone: () => loadCaseStudy(repoId),
    onError: () => {
      if (el) el.innerHTML = '<div class="empty-state" role="alert">Regeneration status unknown.</div>';
    },
  });
}

/* =========================================================
   Patterns
   ========================================================= */
async function loadPatterns(repoId) {
  // Fix 9: Patterns tab removed from Deep Analysis UI; this function still loads
  // patternsData for _rebuildPatternsChart used by the Overview tab.
  const el = document.getElementById('patterns-content');
  let data;
  try { data = await apiFetch(`/api/repos/${encodeURIComponent(repoId)}/patterns`); }
  catch { return; }
  patternsData = data;
  if (!el) { _rebuildPatternsChart(); return; } // tab removed, just update chart data
  el.innerHTML = spinner();
  let html = '';

  const confHotspots = (data.hotspots || []).filter(h => (h.confidence || 0) >= 0.7);
  html += `<div class="section-heading" data-tip="secHotspots" tabindex="0">Hotspots</div>`;
  if (confHotspots.length > 0) {
    const top10 = confHotspots.slice(0, 10);
    html += `<div class="chart-box" style="margin-bottom:0.5rem">
      <div class="chart-container" style="height:${Math.max(120, top10.length * 32)}px">
        <canvas id="chart-hotspots-patterns" aria-label="Horizontal bar chart of top hotspot files, colored by confidence level"></canvas>
      </div>
    </div>`;
    html += `<div id="hs-evidence-simple" style="margin-bottom:1rem">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.5rem">
        <span style="font-size:12px;color:var(--muted)">${confHotspots.length} high-confidence hotspot${confHotspots.length !== 1 ? 's' : ''}</span>
        <button style="font-size:11px;font-weight:700;background:var(--accent);color:#fff;border:none;border-radius:5px;padding:0.25rem 0.7rem;cursor:pointer" onclick="_toggleEvidenceMode()">Full table ↓</button>
      </div>
      <div style="display:flex;flex-direction:column;gap:0.4rem">`
    + confHotspots.map(h => {
        const fname = h.file_path.split('/').pop();
        const conf = h.confidence || 0;
        const analyzed = (h.evidence_commit_shas || []).length;
        const color = conf >= 0.85 ? '#ef4444' : conf >= 0.7 ? '#eab308' : '#22c55e';
        const shas = h.evidence_commit_shas || [];
        return `<div style="display:flex;align-items:center;gap:0.6rem;padding:0.4rem 0.6rem;background:var(--surface);border-radius:6px;border-left:3px solid ${color}" title="${esc(h.file_path)}">
          <code style="font-size:12px;flex:1;cursor:pointer" onclick="_searchCommitsByFile(${JSON.stringify(h.file_path)})">${esc(fname)}</code>
          <span style="font-size:11px;color:var(--muted)">${h.commit_count} commits</span>
          ${analyzed ? `<button data-shas="${esc(JSON.stringify(shas))}" data-label="Hotspot: ${esc(fname)}" onclick="_filterHotspot(this)" style="font-size:11px;color:var(--accent);background:none;border:none;cursor:pointer;padding:0">${analyzed} analyzed →</button>` : ''}
        </div>`;
      }).join('')
    + `</div></div>`;
    // Detail mode (full table — hidden by default)
    html += `<div id="hs-evidence-detail" style="display:none;margin-bottom:1rem">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.5rem">
        <span style="font-size:12px;color:var(--muted)">${confHotspots.length} files · click a row to view analyzed commits</span>
        <button style="font-size:11px;font-weight:700;background:var(--accent);color:#fff;border:none;border-radius:5px;padding:0.25rem 0.7rem;cursor:pointer" onclick="_toggleEvidenceMode()">Summary ↑</button>
      </div>
      <div class="table-wrap">
      <table aria-label="Hotspot files">
        <thead><tr><th scope="col">File</th><th scope="col" title="Commits touching this file (all history)">Total commits</th><th scope="col" title="Commits with AI analysis available — click to view them">Analyzed</th><th scope="col">Confidence</th></tr></thead><tbody>`;
    confHotspots.forEach(h => {
      const pct = h.confidence != null ? (h.confidence * 100).toFixed(0) + '%' : '—';
      const conf = h.confidence || 0;
      const analyzedCount = (h.evidence_commit_shas || []).length;
      const fname = h.file_path.split('/').pop();
      const analyzedLabel = analyzedCount > 0
        ? `<button data-shas="${esc(JSON.stringify(h.evidence_commit_shas||[]))}" data-label="Hotspot: ${esc(fname)}" onclick="event.stopPropagation();_filterHotspot(this)" style="font-size:12px;color:var(--accent);background:none;border:none;cursor:pointer;padding:0">${analyzedCount} →</button>`
        : `<span style="color:var(--muted)">0</span>`;
      html += `<tr title="${esc(h.file_path)} — ${h.commit_count} total commits, ${analyzedCount} analyzed">
        <td><code style="font-size:11px">${esc(fname)}</code><div style="font-size:10px;color:var(--muted)">${esc(h.file_path)}</div></td>
        <td>${h.commit_count}</td>
        <td>${analyzedLabel}</td>
        <td><span style="color:${conf>=0.85?'#ef4444':conf>=0.7?'#eab308':'#22c55e'}">${pct}</span></td>
      </tr>`;
    });
    html += `</tbody></table></div></div>`;
  } else { html += '<div class="empty-state">No hotspots detected.</div>'; }

  const signalDefs = [];
  if (data.refactor_wave) signalDefs.push({ icon: '🔁', name: 'Refactor Wave', tip: 'sigRefactor', obj: data.refactor_wave, color: '#f97316', desc: d => `${d.commit_count||0} refactor commits · ${((d.ratio||0)*100).toFixed(1)}% of analyzed` });
  if (data.test_growth_signal) signalDefs.push({ icon: '🧪', name: 'Test Growth', tip: 'sigTest', obj: data.test_growth_signal, color: '#22c55e', desc: d => `test:bug ratio ${(d.ratio||0).toFixed(2)} · Growing test coverage` });
  if (signalDefs.length > 0) {
    html += `<div class="section-heading" data-tip="statPatterns" tabindex="0">Pattern Signals</div><div class="signal-cards-row">`;
    signalDefs.forEach(s => {
      const big = s.obj.commit_count != null ? s.obj.commit_count : (s.obj.count != null ? s.obj.count : ((s.obj.ratio||0)*100).toFixed(0)+'%');
      html += `<div class="signal-card" style="border-left-color:${s.color}" data-tip="${s.tip}" tabindex="0">
        <div class="sc-icon" aria-hidden="true">${s.icon}</div>
        <div class="sc-name">${esc(s.name)}</div>
        <div class="sc-count" style="color:${s.color}" aria-label="${esc(s.name)}: ${big}">${big}</div>
        <div class="sc-desc">${esc(s.desc(s.obj))}</div>
      </div>`;
    });
    html += '</div>';
  }

  const realRecurrences = (data.bugfix_recurrences || []).filter(r => (r.commit_count || r.count || r.occurrences || 0) > 1);
  if (realRecurrences.length > 0) {
    html += `<div class="section-heading" data-tip="sigBugfixRec" tabindex="0">🐛 Recurring Bug Areas</div>`;
    html += `<p style="font-size:12px;color:var(--muted);margin-bottom:0.75rem">Same files or components fixed multiple times — a sign of deeper instability or architectural debt.</p>`;
    realRecurrences.forEach(r => {
      const file = r.file_path || r.component || r.area || r.name || '?';
      const count = r.commit_count || r.count || r.occurrences || 0;
      const first = r.first_seen ? r.first_seen.slice(0, 10) : null;
      const last = r.last_seen ? r.last_seen.slice(0, 10) : null;
      const msgs = Array.isArray(r.commit_messages) ? r.commit_messages : (Array.isArray(r.messages) ? r.messages : []);
      html += `<div class="bugfix-rec-card" style="cursor:pointer" data-kw="${esc(file)}" onclick="_searchCommitsByKeyword(this.dataset.kw)">
        <div class="brc-top">
          <code class="brc-file">${esc(file)}</code>
          <span class="brc-count" style="color:#ef4444">${count}× fixed</span>
        </div>
        ${first ? `<div class="brc-range">${first}${last && last !== first ? ` → ${last}` : ''}</div>` : ''}
        ${msgs.length ? `<ul class="brc-msgs">${msgs.slice(0,3).map(m => `<li>${esc((m||'').slice(0,100))}</li>`).join('')}</ul>` : ''}
      </div>`;
    });
  }

  if (data.dependency_migrations && data.dependency_migrations.length > 0) {
    html += `<div class="section-heading" data-tip="secMigrations" tabindex="0">Dependency Migrations</div>`;
    data.dependency_migrations.forEach(m => {
      const from = m.from_dependency || m.from_dep || m.from || '?';
      const to = m.to_dependency || m.to_dep || m.to || '?';
      const count = m.commit_count || m.commits || 0;
      const conf = m.confidence != null ? `confidence: ${(m.confidence*100).toFixed(0)}%` : '';
      html += `<div class="migration-row">
        <span class="from-dep">${esc(from)}</span><span class="arrow" aria-hidden="true">──→</span><span class="to-dep">${esc(to)}</span>
        ${conf ? `<span class="m-conf" data-tip="migConf" tabindex="0">${esc(conf)}</span>` : ''}
        <span class="m-count" aria-label="${count} commits">${count}</span>
      </div>`;
    });
  }

  if (data.explanations && data.explanations.length > 0) {
    html += `<div class="section-heading" data-tip="secInsights" tabindex="0">💡 Educational Insights</div>`;
    data.explanations.forEach(ex => {
      html += `<div class="insight-card">
        <div class="insight-title">💡 ${esc(ex.pattern_type || ex.title || 'Insight')}</div>
        ${ex.why_it_matters ? `<div class="insight-label">Why it matters</div><p>${esc(ex.why_it_matters)}</p>` : ''}
        ${ex.engineer_takeaway ? `<div class="insight-label">Engineer takeaway</div><p><em>${esc(ex.engineer_takeaway)}</em></p>` : ''}
      </div>`;
    });
  }

  if (!html) html = '<div class="empty-state">No patterns detected yet.</div>';
  el.innerHTML = html;

  _rebuildPatternsChart();
}

function _toggleEvidenceMode() {
  const simple = document.getElementById('hs-evidence-simple');
  const detail = document.getElementById('hs-evidence-detail');
  if (!simple || !detail) return;
  const showingSimple = detail.style.display === 'none';
  simple.style.display = showingSimple ? 'none' : '';
  detail.style.display = showingSimple ? '' : 'none';
}

function _applyCommitFilter(desc) {
  const bar = document.getElementById('commits-back-bar');
  const descEl = document.getElementById('commits-filter-desc');
  if (bar) bar.style.display = 'flex';
  if (descEl) descEl.textContent = desc;
  renderCommitsTable(allCommits, allCommits.length);
}

function _clearCommitFilters() {
  const sel = document.getElementById('cat-filter');
  const kw = document.getElementById('keyword-filter');
  if (sel) sel.value = '';
  if (kw) kw.value = '';
  _evidenceShaFilter = null;
  const bar = document.getElementById('commits-back-bar');
  if (bar) bar.style.display = 'none';
  renderCommitsTable(allCommits, allCommits.length);
}

function _filterHotspot(btn) {
  try {
    const shas = JSON.parse(btn.dataset.shas || '[]');
    _filterByEvidenceShas(shas, btn.dataset.label || 'Hotspot');
  } catch {}
}

async function _filterByEvidenceShas(shas, label) {
  if (!currentRepo || !shas || !shas.length) return;
  switchView('detail');
  switchTab('commits');
  // Fetch all analyzed commits so SHA filter doesn't silently miss any
  if (commitsLimit < 1000) {
    commitsLimit = 1000;
    await loadCommits(currentRepo, false);
  }
  _evidenceShaFilter = new Set(shas);
  _applyCommitFilter(label);
}

function _searchCommitsByFile(filePath) {
  if (!currentRepo) return;
  const keyword = filePath.split('/').pop();
  switchView('detail');
  switchTab('commits');
  setTimeout(() => {
    const input = document.getElementById('keyword-filter');
    if (input) { input.value = keyword; _applyCommitFilter(`File: ${keyword}`); }
  }, 100);
}

function _searchCommitsByKeyword(keyword) {
  if (!currentRepo) return;
  // Fix 7: Extract SHAs from section text if available (data-kw might be the title,
  // but the button may also carry data-body with the actual section text)
  // Pick the longest meaningful technical word from the title (most specific)
  const stop = new Set(['through','about','those','these','their','there','where','which','would','could','should','after','before','since','until','while','other','first','second','third','using','being','having','making','during','within','after','before','between']);
  const words = keyword.split(/[\s,\/\-:]+/).filter(w => w.length > 4 && !stop.has(w.toLowerCase()));
  const kw = (words.sort((a,b) => b.length - a.length)[0] || keyword.split(/\s+/)[0]).replace(/[^\w]/g, '').toLowerCase();
  switchView('detail');
  switchTab('commits');
  setTimeout(() => {
    const input = document.getElementById('keyword-filter');
    if (!input) return;
    input.value = kw;
    _applyCommitFilter(`Component: ${kw}`);
  }, 200);
}

// Fix 7: Search by SHAs extracted from section body text
function _searchCommitsBySectionBody(bodyText, label) {
  if (!currentRepo) return;
  // Extract 7-40 char hex strings from the body text
  const shaMatches = (bodyText || '').match(/\b[0-9a-f]{7,40}\b/gi) || [];
  const uniqueShas = [...new Set(shaMatches.map(s => s.toLowerCase()))];
  if (uniqueShas.length > 0) {
    // Filter to SHAs that actually exist in loaded commits
    const matchingShas = allCommits
      .filter(c => uniqueShas.some(s => (c.sha || '').toLowerCase().startsWith(s)))
      .map(c => c.sha);
    if (matchingShas.length > 0) {
      _filterByEvidenceShas(matchingShas, label);
      return;
    }
  }
  // Fallback: use keyword search on body text for technical terms
  const stop = new Set(['through','about','those','these','their','there','where','which','would','could','should','after','before','since','until','while','other','first','second','third','using','being','having','making','during','within']);
  const bodyWords = (bodyText || '').split(/[\s,\/\-:.\(\)]+/).filter(w => w.length > 4 && /[a-z]/i.test(w) && !stop.has(w.toLowerCase()) && !/^[0-9a-f]{7,}$/i.test(w));
  const kw = (bodyWords.sort((a,b) => b.length - a.length)[0] || label).replace(/[^\w]/g, '').toLowerCase();
  switchView('detail');
  switchTab('commits');
  setTimeout(() => {
    const input = document.getElementById('keyword-filter');
    if (!input) return;
    input.value = kw;
    _applyCommitFilter(`Section: ${label}`);
  }, 200);
}

function _rebuildPatternsChart() {
  const canvas = document.getElementById('chart-hotspots-patterns');
  if (!canvas || !patternsData) return;
  const confHotspots = (patternsData.hotspots || []).filter(h => (h.confidence || 0) >= 0.7);
  const top10 = confHotspots.slice(0, 10);
  if (!top10.length) return;
  const _tc = () => getComputedStyle(document.documentElement).getPropertyValue('--muted').trim() || '#94a3b8';
  const _tcy = () => getComputedStyle(document.documentElement).getPropertyValue('--text').trim() || '#e2e8f0';
  const _gc = () => getComputedStyle(document.documentElement).getPropertyValue('--border').trim() || '#2d3148';
  destroyChart('hotspots-patterns');
  _charts['hotspots-patterns'] = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: top10.map(h => h.file_path.split('/').pop()),
      datasets: [{ label: 'Commits', data: top10.map(h => h.commit_count), backgroundColor: top10.map(h => { const c=h.confidence||0; return c>=0.7?'#ef4444':c>=0.4?'#eab308':'#22c55e'; }), borderRadius: 3 }],
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { footer: () => 'Click to view related commits' } } },
      scales: {
        x: { ticks: { color: _tc(), font: { size: 10 } }, grid: { color: _gc() } },
        y: { ticks: { color: _tcy(), font: { size: 11 } }, grid: { display: false } },
      },
      onClick(evt, els) {
        if (!els.length) return;
        const h = top10[els[0].index];
        if (h) _searchCommitsByFile(h.file_path);
      },
    },
  });
}

/* =========================================================
   Commits
   ========================================================= */
async function loadCommits(repoId, append) {
  const el = document.getElementById('commits-content');
  const btn = document.getElementById('load-more-btn');
  if (!append) { el.innerHTML = spinner(); btn.style.display = 'none'; allCommits = []; }
  let data;
  try { data = await apiFetch(`/api/repos/${encodeURIComponent(repoId)}/commits?limit=${commitsLimit}&order=newest`); }
  catch { el.innerHTML = '<div class="empty-state" role="alert">Error loading commits.</div>'; return; }
  allCommits = data.commits || [];
  renderCommitsTable(allCommits, data.total);
}

function renderCommitsTable(commits, total) {
  const el = document.getElementById('commits-content');
  const btn = document.getElementById('load-more-btn');
  const catFilter = document.getElementById('cat-filter').value;
  const keyword = document.getElementById('keyword-filter').value.toLowerCase();
  let filtered = commits;
  if (_evidenceShaFilter) filtered = filtered.filter(c => _evidenceShaFilter.has(c.sha));
  if (catFilter) filtered = filtered.filter(c => (c.category || '').toUpperCase() === catFilter);
  if (keyword) filtered = filtered.filter(c =>
    (c.message||'').toLowerCase().includes(keyword) ||
    (c.summary||'').toLowerCase().includes(keyword) ||
    (c.sha||'').toLowerCase().includes(keyword) ||
    (c.affected_components||[]).some(ac => ac.toLowerCase().includes(keyword)) ||
    (c.files_changed||[]).some(f => f.toLowerCase().includes(keyword))
  );
  if (filtered.length === 0) {
    el.innerHTML = `<div class="empty-state">
      <p>No commits match "<strong>${esc(keyword || catFilter)}</strong>".</p>
      <p style="margin-top:0.5rem;font-size:12px;color:var(--muted)">Only analyzed commits are searchable. Analyze more to expand coverage.</p>
      <div style="margin-top:0.75rem;display:flex;gap:0.5rem;justify-content:center">
        <button class="analyze-btn" style="font-size:12px;padding:0.3rem 0.7rem" onclick="_clearCommitFilters()">Clear filter</button>
        <button class="analyze-btn" style="font-size:12px;padding:0.3rem 0.7rem" onclick="switchTab('overview')">← Overview</button>
        <button class="analyze-btn" style="font-size:12px;padding:0.3rem 0.7rem" onclick="triggerAnalyze()">+ Analyze more</button>
      </div>
    </div>`;
    btn.style.display = 'none'; return;
  }

  let rows = '';
  filtered.forEach((c, i) => {
    const sha7 = (c.sha || '').slice(0, 7);
    const cat = (c.category || '').toUpperCase();
    const bClass = badgeClass(c.category || '');
    const catKey = catTipKey(c.category || '');
    const riskKey = riskTipKey(c.importance || '');
    const importance = c.importance
      ? `<span class="badge" style="background:#1e293b;color:${c.importance==='high'?'#ef4444':c.importance==='medium'?'#eab308':'#6ee7b7'}" data-tip="${riskKey}" tabindex="0">${esc(c.importance.toUpperCase())}</span>`
      : '';
    const summary = truncate(c.summary || c.message || '', 80);
    const expandId = `expand-${i}`;
    rows += `<tr class="clickable-row" onclick="toggleExpand('${expandId}')" aria-expanded="false">
      <td><span class="sha-code">${esc(sha7)}</span></td>
      <td class="date-cell">${fmtDate(c.committed_at)}</td>
      <td>${cat ? `<span class="badge ${bClass}" data-tip="${catKey}" tabindex="0">${esc(cat)}</span>` : '<span aria-label="uncategorized">—</span>'} ${importance}</td>
      <td class="summary-cell" title="${esc(c.summary || c.message || '')}">${esc(summary)}</td>
    </tr>
    <tr class="expand-row" id="${expandId}">
      <td colspan="4" class="expand-cell">${esc(c.summary || c.message || '(no summary)')}</td>
    </tr>`;
  });

  el.innerHTML = `<div class="table-wrap"><table aria-label="Analyzed commits">
    <thead><tr>
      <th scope="col">SHA</th><th scope="col">Date</th>
      <th scope="col" data-tip="catUnknown" tabindex="0">Category</th>
      <th scope="col">Summary</th>
    </tr></thead>
    <tbody>${rows}</tbody>
  </table></div>`;

  btn.style.display = (total !== undefined && commits.length < total) ? 'inline-block' : 'none';
  btn.disabled = false;
}

function toggleExpand(id) {
  const r = document.getElementById(id);
  if (!r) return;
  r.classList.toggle('open');
  const row = r.previousElementSibling;
  if (row) row.setAttribute('aria-expanded', r.classList.contains('open') ? 'true' : 'false');
}

document.getElementById('cat-filter').addEventListener('change', () => renderCommitsTable(allCommits, allCommits.length));
document.getElementById('keyword-filter').addEventListener('input', () => renderCommitsTable(allCommits, allCommits.length));
document.getElementById('load-more-btn').addEventListener('click', function() {
  if (!currentRepo) return;
  commitsLimit += 20;
  this.disabled = true;
  this.textContent = 'Loading…';
  loadCommits(currentRepo, false).then(() => { this.textContent = 'Load more'; });
});

/* =========================================================
   Trigger analysis
   ========================================================= */
function _showAnalyzePicker() {
  const picker = document.getElementById('sh-analyze-picker');
  const btn = document.getElementById('sh-analyze-btn');
  if (!picker || !btn) return;
  picker.style.display = 'flex';
  btn.style.display = 'none';
}

function _hideAnalyzePicker() {
  const picker = document.getElementById('sh-analyze-picker');
  const btn = document.getElementById('sh-analyze-btn');
  if (picker) picker.style.display = 'none';
  if (btn) { btn.style.display = ''; btn.disabled = false; btn.textContent = '+ Analyze'; }
}

async function triggerAnalyze() { _showAnalyzePicker(); }

async function _doAnalyze(limit) {
  if (!currentRepo) return;
  _hideAnalyzePicker();
  const btn = document.getElementById('sh-analyze-btn');

  // Use pre-fetched estimate (available instantly); fall back to API only if not ready yet
  let est = _analyzePrefetch;
  if (!est) {
    try { est = await apiFetch(`/api/repos/${encodeURIComponent(currentRepo)}/analyze/estimate?limit=9999`); _analyzePrefetch = est; } catch {}
  }
  if (est) {
    if (est.unanalyzed_commits === 0) { alert('All commits are already analyzed!'); return; }
    // Scale calls/cost proportionally for the chosen limit
    const effective = limit >= 9999 ? est.unanalyzed_commits : Math.min(limit, est.unanalyzed_commits);
    const ratio = est.unanalyzed_commits > 0 ? effective / est.unanalyzed_commits : 0;
    const scaledCalls = Math.ceil((est.estimated_llm_calls || 0) * ratio);
    const costPerCall = est.estimated_llm_calls > 0 ? (est.estimated_analysis_cost_usd || 0) / est.estimated_llm_calls : 0;
    const scaledCost = scaledCalls * costPerCall + (est.estimated_narrative_cost_usd || 0);
    const costMsg = scaledCost > 0 ? ` (~$${scaledCost.toFixed(4)})` : '';
    const label = limit >= 9999 ? 'all remaining' : `up to ${limit}`;
    if (!confirm(`Analyze ${label} commits?\n${scaledCalls} LLM call(s) needed${costMsg}.\nThis runs in the background.`)) return;
  }
  if (btn) { btn.textContent = 'Running…'; btn.disabled = true; btn.style.color = 'var(--yellow)'; btn.style.display = ''; }
  try {
    const res = await fetch(`/api/repos/${encodeURIComponent(currentRepo)}/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ limit, audience: localStorage.getItem('cs-audience') || 'beginner' }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    _pollAnalyzeStatus(currentRepo);
  } catch (e) {
    alert(`Analysis failed: ${e.message}`);
    if (btn) { btn.textContent = '+ Analyze'; btn.disabled = false; btn.style.color = ''; }
  }
}

function _pollAnalyzeStatus(repoId) {
  const btn = document.getElementById('sh-analyze-btn');
  pollUntilDone({
    url: `/api/repos/${encodeURIComponent(repoId)}/analyze/status`,
    interval: 2000,
    onTick: (s) => {
      if (!btn) return true;  // button removed from DOM — stop silently
      if (s.running) {
        if (s.total > 0 && s.done >= s.total) {
          btn.textContent = 'Updating case study…';
        } else if (s.total > 0) {
          btn.textContent = `${s.done}/${s.total} analyzed`;
        } else {
          btn.textContent = 'Running…';
        }
        return false;
      }
      return true;
    },
    onDone: async () => {
      if (!btn) return;  // guard: button removed while polling
      btn.textContent = '✓ Done!';
      btn.style.color = 'var(--green)';
      btn.disabled = false;
      // Update analyzed count in header
      try {
        const updated = await apiFetch(`/api/repos/${encodeURIComponent(repoId)}/analyze/estimate?limit=9999`);
        _analyzePrefetch = updated;
        const analyzedEl = document.getElementById('sh-analyzed');
        if (analyzedEl) analyzedEl.textContent = (updated.analyzed_commits || 0) + ' analyzed';
      } catch {}
      // Always reload timeline so _tlAllCommits is fresh regardless of which view is active
      if (currentRepo === repoId) loadTimeline(repoId);
      // Reload commits tab if active
      if (document.getElementById('tab-commits')?.classList.contains('active')) loadCommits(repoId, false);
      // Reload case study — regenerated on backend after analysis
      if (currentRepo === repoId) loadCaseStudy(repoId);
      // Reset button after showing Done
      setTimeout(() => {
        if (btn) { btn.textContent = '+ Analyze'; btn.style.color = ''; }
      }, 3000);
    },
    onError: () => {
      if (btn) { btn.textContent = '+ Analyze'; btn.disabled = false; btn.style.color = ''; }
    },
  });
}

/* =========================================================
   Contributors
   ========================================================= */
async function loadContributors(repoId) {
  const el = document.getElementById('contributors-content');
  el.innerHTML = spinner();
  let data;
  try { data = await apiFetch(`/api/repos/${encodeURIComponent(repoId)}/contributors`); }
  catch (e) {
    el.innerHTML = e.status === 404
      ? '<div class="empty-state">No contributor data available.</div>'
      : '<div class="empty-state" role="alert">Error loading contributors.</div>';
    return;
  }

  const all = data.contributors || [];
  const humans = all.filter(c => !c.is_bot);
  const bots = all.filter(c => c.is_bot);

  let html = `<p style="font-size:12px;color:var(--muted);margin-bottom:1rem">
    <strong style="color:var(--text)">${humans.length}</strong> human contributor${humans.length !== 1 ? 's' : ''}
    ${bots.length ? ` · <strong style="color:var(--text)">${bots.length}</strong> bot${bots.length !== 1 ? 's' : ''} (not shown)` : ''}
    <span style="color:var(--border)">·</span> categories based on analyzed sample only
  </p>`;

  html += '<div class="contributor-grid">';
  humans.forEach(c => {
    const initials = c.author_name.split(/\s+/).map(w => w[0] || '').join('').slice(0, 2).toUpperCase() || '?';
    const bgColors = ['#6366f1','#22c55e','#f97316','#a855f7','#3b82f6','#ef4444','#eab308'];
    const bg = bgColors[c.author_name.charCodeAt(0) % bgColors.length];
    const dateRange = (c.first_commit && c.last_commit && c.first_commit !== c.last_commit)
      ? `${c.first_commit} → ${c.last_commit}`
      : (c.first_commit || '—');
    const cats = Object.entries(c.category_counts || {}).sort((a,b) => b[1]-a[1]).slice(0, 5);
    const topFiles = (c.top_files || []).slice(0, 3);
    const isGitHub = (currentRepoMeta?.canonical_url || '').includes('github.com');
    const ghUrl = c.github_username
      ? `https://github.com/${encodeURIComponent(c.github_username)}`
      : `https://github.com/search?q=${encodeURIComponent(c.author_name)}&type=users`;
    const ghLabel = c.github_username ? `@${esc(c.github_username)} ↗` : 'Search on GitHub ↗';
    html += `<div class="contributor-card">
      <div class="cc-top">
        <div class="cc-avatar" style="background:${bg}" aria-hidden="true">${esc(initials)}</div>
        <div style="flex:1">
          <div class="cc-name">${esc(c.author_name)}</div>
          <div class="cc-meta">${c.active_days} active day${c.active_days !== 1 ? 's' : ''}${isGitHub ? ` · <a href="${ghUrl}" target="_blank" rel="noopener" style="color:var(--accent);text-decoration:none;font-size:13px;font-weight:600;padding:0.1rem 0.3rem;border:1px solid var(--accent);border-radius:4px;white-space:nowrap">${ghLabel}</a>` : ''}</div>
        </div>
      </div>
      <div class="cc-stats">
        <span><strong>${c.commit_count}</strong> commits</span>
        <span style="font-size:10px;color:var(--muted)">${dateRange}</span>
      </div>
      ${cats.length ? `<div class="cc-cats">${cats.map(([cat, cnt]) => `<span class="badge ${badgeClass(cat)}" title="${cnt} commits">${esc(cat)}</span>`).join('')}</div>` : ''}
      ${topFiles.length ? `<div class="cc-files" style="flex-wrap:wrap;overflow:hidden;max-width:100%">Top files: ${topFiles.map(f => `<code style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:inline-block;vertical-align:bottom">${esc(f.split('/').pop())}</code>`).join('')}</div>` : ''}
    </div>`;
  });
  html += '</div>';
  el.innerHTML = html;
}

/* =========================================================
   Boot
   ========================================================= */
async function boot() {
  await loadRepos();
  renderRepoCards();
}
boot();
