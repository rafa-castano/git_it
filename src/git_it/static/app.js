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
   Debounce utility
   ========================================================= */
function debounce(fn, ms) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}
const _debouncedTimelineFilter = debounce(_applyTimelineFilters, 150);

/* =========================================================
   Resizable sidebar (drag-to-resize)
   ========================================================= */
const SIDEBAR_MIN_WIDTH = 150;
const SIDEBAR_MAX_WIDTH = 480;
const SIDEBAR_ARROW_STEP = 10;
const SIDEBAR_WIDTH_STORAGE_KEY = 'sidebar-width';

/**
 * Pure clamp so the sidebar can never collapse to nothing or eat the screen.
 * No DOM access here on purpose — keeps this reviewable/testable in isolation.
 */
function clampSidebarWidth(px, min = SIDEBAR_MIN_WIDTH, max = SIDEBAR_MAX_WIDTH) {
  const n = Number(px);
  if (!Number.isFinite(n)) return min;
  return Math.min(Math.max(n, min), max);
}

function _setSidebarWidth(px) {
  const clamped = clampSidebarWidth(px);
  document.documentElement.style.setProperty('--sidebar-width', `${clamped}px`);
  localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(clamped));
  const handle = document.getElementById('sidebar-resize-handle');
  if (handle) handle.setAttribute('aria-valuenow', String(clamped));
  return clamped;
}

function _initSidebarResize() {
  const handle = document.getElementById('sidebar-resize-handle');
  const aside = document.querySelector('#repo-view aside');
  if (!handle || !aside) return;

  // Restore persisted width (falls back to the CSS default when unset/invalid).
  const stored = parseInt(localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY), 10);
  if (Number.isFinite(stored)) _setSidebarWidth(stored);

  let dragging = false;
  let startX = 0;
  let startWidth = 0;

  const onPointerMove = (e) => {
    if (!dragging) return;
    _setSidebarWidth(startWidth + (e.clientX - startX));
  };
  const stopDragging = () => {
    if (!dragging) return;
    dragging = false;
    handle.classList.remove('dragging');
    document.removeEventListener('mousemove', onPointerMove);
    document.removeEventListener('mouseup', stopDragging);
  };

  handle.addEventListener('mousedown', (e) => {
    dragging = true;
    startX = e.clientX;
    startWidth = aside.getBoundingClientRect().width;
    handle.classList.add('dragging');
    document.addEventListener('mousemove', onPointerMove);
    document.addEventListener('mouseup', stopDragging);
    e.preventDefault();
  });

  handle.addEventListener('keydown', (e) => {
    const current = aside.getBoundingClientRect().width;
    if (e.key === 'ArrowLeft') {
      _setSidebarWidth(current - SIDEBAR_ARROW_STEP);
      e.preventDefault();
    } else if (e.key === 'ArrowRight') {
      _setSidebarWidth(current + SIDEBAR_ARROW_STEP);
      e.preventDefault();
    }
  });
}

document.addEventListener('DOMContentLoaded', _initSidebarResize);

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
  tlLegacySummary: "This commit was analyzed before beginner/expert summaries existed, so the Beginner/Expert selector has no effect on it — re-analyze the repository to generate audience-specific versions.",
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
  let text = TIPS[key] || key;
  // Elements that also act as a click target (and no longer carry a native
  // title=, to avoid a double tooltip) can append a click-action hint here
  // without mutating the shared TIPS entry used by non-interactive contexts.
  if (el.dataset.tipSuffix) text += '\n' + el.dataset.tipSuffix;
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

document.documentElement.classList.add('tips-enabled');
document.getElementById('btn-tips').addEventListener('click', function() {
  _tipsEnabled = !_tipsEnabled;
  _hideTip();
  this.classList.toggle('active', _tipsEnabled);
  this.setAttribute('aria-pressed', _tipsEnabled ? 'true' : 'false');
  this.querySelector('.btn-tips-label').textContent = _tipsEnabled ? 'Hide Tooltips' : 'Show Tooltips';
  document.documentElement.classList.toggle('tips-enabled', _tipsEnabled);
});

// showPicker() forces the native date calendar open reliably across environments
['tl-date-from', 'tl-date-to'].forEach(id => {
  document.getElementById(id)?.addEventListener('click', function() { this.showPicker?.(); });
});
// Activity chart date pickers are added dynamically by loadOverview; delegate to document
document.addEventListener('click', e => {
  if (e.target.matches('#activity-date-from, #activity-date-to')) e.target.showPicker?.();
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
let _evidenceShaFilter = null;
let patternsData = null;
let detailLoaded = false;
let _ingestPoll = null;
let _analyzePoll = null;
let _analyzePrefetch = null;
const UPDATED_ANALYSIS_TABS = new Set(['overview', 'case-study', 'commits']);
let _updatedTabs = new Set();

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
/* Commit-categories donut multi-select (spec 018): clicking a donut slice or
   legend item toggles that category in/out of a selected set; the donut
   shows only the selected categories (all, when the set is empty). These two
   functions are pure/DOM-free so the selection logic is reviewable and
   testable in principle -- see spec 018 AC-01/AC-02/AC-03. */
/** Returns a NEW Set with `cat` toggled in/out of `set` (added if absent,
 *  removed if present). Does not mutate `set`. */
function toggleSelection(set, cat) {
  const next = new Set(set);
  if (next.has(cat)) next.delete(cat); else next.add(cat);
  return next;
}

/** Returns the subset of `catCounts` (`{category, count}` entries) whose
 *  upper-cased category is in `selected`. When `selected` is empty/falsy,
 *  returns `catCounts` unchanged (the default show-all view). */
function visibleCategories(catCounts, selected) {
  if (!selected || selected.size === 0) return catCounts;
  return catCounts.filter(c => selected.has((c.category || '').toUpperCase()));
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
/* Spec 016: deterministic answer-formatting safety net, mirrored exactly from
   `normalize_answer_text()` in src/git_it/chat/service.py. Fixes two LLM
   answer defects before markdown parsing: (1) a missing space after a
   sentence-ending period/question mark/exclamation mark when immediately
   followed by an uppercase letter (e.g. "evidence.The next" -> "evidence. The
   next"), and (2) three-or-more consecutive newlines collapsed to one blank
   line. Conservative by design: rule 1 only fires when the character before
   the punctuation is a lowercase letter, which naturally spares decimals
   (3.12), ellipses (...), and most abbreviations/URLs. Text inside fenced
   code blocks (```...```) is never rewritten by either rule.
   These two implementations (this one and the Python one) MUST stay in sync —
   if one changes, update the other. */
function normalizeAnswerText(text) {
  const body = text || '';
  if (!body) return '';
  const parts = body.split(/(```[\s\S]*?```)/);
  return parts
    .map((part, i) => {
      if (i % 2 === 1) return part; // fenced code block, verbatim
      return part
        .replace(/([a-z])([.?!])([A-Z])/g, '$1$2 $3')
        .replace(/\n{3,}/g, '\n\n');
    })
    .join('');
}
/* ADR 013: the one path that renders LLM-generated Markdown. Fails safe (escaped
   plain text), never open (unsanitized HTML), if marked/DOMPurify fail to load. */
function renderMarkdown(text, fallbackTag) {
  const body = normalizeAnswerText(text || '');
  if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') {
    const tag = fallbackTag || 'pre';
    return `<${tag}>${esc(body)}</${tag}>`;
  }
  return DOMPurify.sanitize(marked.parse(body));
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
function _extractIsoDate(text) {
  const M = { jan:'01',feb:'02',mar:'03',apr:'04',may:'05',jun:'06',
               jul:'07',aug:'08',sep:'09',oct:'10',nov:'11',dec:'12' };
  let m;
  m = text.match(/\b(\d{4}-\d{2}-\d{2})\b/);
  if (m) return m[1];
  m = text.match(/\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+(\d{4})\b/i);
  if (m) return `${m[3]}-${M[m[2].slice(0,3).toLowerCase()]}-${m[1].padStart(2,'0')}`;
  m = text.match(/\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+(\d{1,2}),?\s+(\d{4})\b/i);
  if (m) return `${m[3]}-${M[m[1].slice(0,3).toLowerCase()]}-${m[2].padStart(2,'0')}`;
  m = text.match(/\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+(\d{4})\b/i);
  if (m) return `${m[2]}-${M[m[1].slice(0,3).toLowerCase()]}-01`;
  return null;
}

/* Activity chart zoom ladder (spec 017): ordered coarsest -> finest scales,
   used by bucketKey()/buildActivityData() for bucketing and by
   scaleCoarser()/scaleFiner() to step the manual zoom controls. */
const ACTIVITY_SCALES = ['year', 'month', 'week', 'day', 'hour'];

/** One step coarser than `scale` (more zoomed out), or null at the coarsest
 *  scale ('year') or an unrecognized scale. */
function scaleCoarser(scale) {
  const i = ACTIVITY_SCALES.indexOf(scale);
  return i > 0 ? ACTIVITY_SCALES[i - 1] : null;
}

/** One step finer than `scale` (more zoomed in), or null at the finest scale
 *  ('hour') or an unrecognized scale. */
function scaleFiner(scale) {
  const i = ACTIVITY_SCALES.indexOf(scale);
  return i !== -1 && i < ACTIVITY_SCALES.length - 1 ? ACTIVITY_SCALES[i + 1] : null;
}

function _parseYMD(dateStr) {
  const [y, m, d] = dateStr.slice(0, 10).split('-').map(Number);
  return { y, m, d };
}
function _fmtYMD(date) {
  return date.toISOString().slice(0, 10);
}

/** ISO-8601 week key ("YYYY-Www", Monday-start, week 1 = the week containing
 *  the year's first Thursday). Computed via UTC calendar arithmetic on the
 *  date-only (Y-M-D) portion of the input -- never via local-timezone Date
 *  parsing -- to match this file's existing convention of slicing
 *  committed_at strings directly rather than round-tripping them through a
 *  timezone-sensitive Date. */
function isoWeekKey(dateStr) {
  const { y, m, d } = _parseYMD(dateStr);
  const date = new Date(Date.UTC(y, m - 1, d));
  const dayNum = date.getUTCDay() || 7; // Mon=1..Sun=7
  date.setUTCDate(date.getUTCDate() + 4 - dayNum); // Thursday of the same ISO week
  const isoYear = date.getUTCFullYear();
  const yearStart = new Date(Date.UTC(isoYear, 0, 1));
  const week = Math.ceil((((date - yearStart) / 86400000) + 1) / 7);
  return `${isoYear}-W${String(week).padStart(2, '0')}`;
}

/** Inverse of isoWeekKey: the Monday (as a UTC Date) that starts ISO week `key`. */
function isoWeekStart(key) {
  const [yearStr, weekStr] = key.split('-W');
  const isoYear = Number(yearStr);
  const week = Number(weekStr);
  const jan4 = new Date(Date.UTC(isoYear, 0, 4));
  const jan4Day = jan4.getUTCDay() || 7;
  const week1Monday = new Date(jan4);
  week1Monday.setUTCDate(jan4.getUTCDate() - (jan4Day - 1));
  const monday = new Date(week1Monday);
  monday.setUTCDate(week1Monday.getUTCDate() + (week - 1) * 7);
  return monday;
}

/** The bucket key for one commit at a given scale. The hour format
 *  ("YYYY-MM-DD HHh") is unchanged from the pre-zoom-ladder format so the
 *  existing Commits-tab hour cross-link (_tlHourFilter) keeps matching
 *  without modification. */
function bucketKey(committedAt, scale) {
  switch (scale) {
    case 'year': return committedAt.slice(0, 4);
    case 'month': return committedAt.slice(0, 7);
    case 'week': return isoWeekKey(committedAt.slice(0, 10));
    case 'hour': return committedAt.slice(0, 13).replace('T', ' ') + 'h';
    case 'day':
    default: return committedAt.slice(0, 10);
  }
}

/** The full calendar span { from, to } (inclusive, "YYYY-MM-DD") covered by
 *  one bucket key at `scale`. Used both to scope a drill-down (click a
 *  column) and to widen the drilled span when zooming out (see
 *  alignSpanToScale). */
function spanForColumn(key, scale) {
  if (scale === 'year') {
    return { from: `${key}-01-01`, to: `${key}-12-31` };
  }
  if (scale === 'month') {
    const [y, m] = key.split('-').map(Number);
    return { from: `${key}-01`, to: new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10) };
  }
  if (scale === 'week') {
    const monday = isoWeekStart(key);
    const sunday = new Date(monday);
    sunday.setUTCDate(monday.getUTCDate() + 6);
    return { from: _fmtYMD(monday), to: _fmtYMD(sunday) };
  }
  if (scale === 'hour') {
    const day = key.slice(0, 10);
    return { from: day, to: day };
  }
  // 'day'
  return { from: key, to: key };
}

/** Widen (or realign) an existing drilled span to the natural bucket
 *  boundaries of a new (coarser) scale -- e.g. a one-week span becomes the
 *  whole containing month when zooming out from 'week' to 'month'. */
function alignSpanToScale(span, scale) {
  if (!span) return null;
  const fromSpan = spanForColumn(bucketKey(span.from + 'T00:00:00', scale), scale);
  const toSpan = spanForColumn(bucketKey(span.to + 'T00:00:00', scale), scale);
  return { from: fromSpan.from, to: toSpan.to };
}

/** Restricts `commits` to those whose committed_at date falls within `span`
 *  (inclusive). A null span means "no restriction" (the full commit set). */
function commitsInSpan(commits, span) {
  if (!span) return commits;
  return commits.filter(c => {
    const d = (c.committed_at || '').slice(0, 10);
    return !!d && d >= span.from && d <= span.to;
  });
}

/** Picks a sensible initial zoom-ladder scale from the spread of `commits`'
 *  committed_at dates. Never auto-selects 'week' -- that rung is reachable
 *  only via drill-down or the manual zoom controls. */
function bestScale(commits) {
  const years = new Set(commits.map(c => (c.committed_at || '').slice(0, 4)).filter(Boolean));
  const months = new Set(commits.map(c => (c.committed_at || '').slice(0, 7)).filter(Boolean));
  const days = new Set(commits.map(c => (c.committed_at || '').slice(0, 10)).filter(Boolean));
  if (days.size <= 1) return 'hour';
  if (months.size <= 2) return 'day';
  if (years.size <= 1) return 'month';
  return 'year';
}

/** Buckets `commits` at `scale` (defaults to bestScale(commits) when omitted). */
function buildActivityData(commits, scale) {
  const g = scale || bestScale(commits);
  const map = {};
  commits.forEach(c => {
    if (!c.committed_at) return;
    const key = bucketKey(c.committed_at, g);
    map[key] = (map[key] || 0) + 1;
  });
  const labels = Object.keys(map).sort();
  return { labels, data: labels.map(k => map[k]), scale: g };
}

/* =========================================================
   Repo loading & sidebar
   ========================================================= */
let reposCache = [];

function renderSidebarRepos() {
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

async function loadRepos() {
  let data;
  try { data = await apiFetch('/api/repos'); }
  catch {
    document.getElementById('sidebar-list').innerHTML =
      '<div class="empty-state" role="alert">Could not load repositories.</div>';
    return;
  }
  reposCache = data.repos || [];
  renderSidebarRepos();
}

/* =========================================================
   Home screen
   ========================================================= */
function renderRepoCards() {
  const grid = document.getElementById('repo-cards-grid');
  const countEl = document.getElementById('repos-count');
  if (reposCache.length === 0) {
    grid.innerHTML = '<div class="empty-state" role="status" style="grid-column:1/-1">No repositories analyzed yet. Paste a GitHub URL above to get started.</div>';
    countEl.textContent = '';
    return;
  }
  countEl.textContent = reposCache.length;
  grid.innerHTML = '';
  reposCache.forEach(repo => {
    grid.appendChild(_buildRepoCard(repo));
  });
}

const _GH_ICON_SVG = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/></svg>`;

// Spec 019: fixed-order categorical palette for the language bar, validated
// (lightness band, CVD-adjacency, contrast) against this app's own --surface
// values via the dataviz skill's validate_palette.js — see
// docs/specs/019-github-stars-languages.md § Domain concepts for why this is a
// dedicated palette rather than a reuse of --blue/--green/--red/etc (those
// already carry fixed status meaning elsewhere in the app). Order is the
// CVD-safety mechanism — do not reshuffle without re-validating.
const _LANG_COLOR_VARS = [
  '--lang-1', '--lang-2', '--lang-3', '--lang-4',
  '--lang-5', '--lang-6', '--lang-7', '--lang-8',
];
const _LANG_BAR_MAX_SEGMENTS = 8;

function _buildLanguageBar(languages) {
  if (!languages || languages.length === 0) return '';
  let shown = languages.slice(0, _LANG_BAR_MAX_SEGMENTS);
  const rest = languages.slice(_LANG_BAR_MAX_SEGMENTS);
  if (rest.length > 0) {
    const otherBytes = rest.reduce((sum, l) => sum + l.bytes, 0);
    const otherPercent = Math.round(rest.reduce((sum, l) => sum + l.percent, 0) * 10) / 10;
    shown = shown.concat([{ language: 'Other', bytes: otherBytes, percent: otherPercent }]);
  }
  const colorFor = (lang, i) => lang === 'Other' ? 'var(--muted)' : `var(${_LANG_COLOR_VARS[i % _LANG_COLOR_VARS.length]})`;
  const segments = shown.map((l, i) => {
    const tip = `${l.language}: ${l.percent}%`;
    return `<span class="rc-lang-seg" style="width:${l.percent}%;background:${colorFor(l.language, i)}" data-tip="${esc(tip)}" tabindex="0" role="img" aria-label="${esc(tip)}"></span>`;
  }).join('');
  const legend = shown.map((l, i) =>
    `<span class="rc-lang-legend-item"><span class="rc-lang-swatch" style="background:${colorFor(l.language, i)}" aria-hidden="true"></span>${esc(l.language)} ${l.percent}%</span>`
  ).join('');
  return `<div class="rc-lang-bar" role="img" aria-label="Language breakdown">${segments}</div><div class="rc-lang-legend">${legend}</div>`;
}

function _buildRepoCard(repo) {
  const short = repoShortName(repo.canonical_url);
  const card = document.createElement('div');
  card.className = 'repo-card';
  card.setAttribute('tabindex', '0');
  card.setAttribute('role', 'listitem');
  card.setAttribute('aria-label', `${short} — ${repo.commit_count} commits, ${repo.analysis_count} analyzed, status: ${repo.status}`);

  const { label: statusLabel, cls: statusCls } = _repoStatusLabel(repo);
  const ghUrl = repo.canonical_url && repo.canonical_url.includes('github.com') ? repo.canonical_url : null;
  const starsHtml = (repo.stars !== null && repo.stars !== undefined)
    ? `<span class="rc-stat" data-tip="${repo.stars.toLocaleString()} GitHub stars" tabindex="0">⭐ ${repo.stars.toLocaleString()}</span>`
    : '';
  const langBarHtml = _buildLanguageBar(repo.languages);
  card.innerHTML = `
    <div class="rc-accent" aria-hidden="true"></div>
    <div class="rc-name">${esc(short)}</div>
    <div class="rc-url">${esc(repo.canonical_url)}</div>
    <div class="rc-stats">
      <span class="rc-stat"><strong>${repo.commit_count}</strong> commits</span>
      <span class="rc-stat"><strong>${repo.analysis_count}</strong> analyzed</span>
      ${starsHtml}
      ${repo.has_case_study ? '<span style="color:var(--green);font-size:12px">✓ Case study</span>' : ''}
    </div>
    ${langBarHtml}
    <div class="rc-footer">
      <span class="rc-status ${statusCls}" aria-label="Status: ${esc(statusLabel)}">${esc(statusLabel)}</span>
      <div style="display:flex;align-items:center;gap:0.5rem">
        ${ghUrl ? `<a href="${esc(ghUrl)}" target="_blank" rel="noopener" class="rc-gh-link" aria-label="View ${esc(short)} on GitHub" title="View on GitHub" onclick="event.stopPropagation()">${_GH_ICON_SVG}</a>` : ''}
        <button class="rc-delete-btn" aria-label="Delete ${esc(short)}" title="Delete repository" onclick="event.stopPropagation(); deleteRepo('${esc(repo.repository_id)}', '${esc(repo.canonical_url)}', this.closest('.repo-card'))">&#x1F5D1;</button>
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
  const statusEl = document.getElementById('ingest-status');
  if (!raw) {
    statusEl.textContent = 'Enter a GitHub URL or owner/repo (e.g. torvalds/linux).';
    statusEl.style.color = 'var(--red)';
    input.focus();
    return;
  }
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
   Refresh all (spec 028) — home-view collection action.
   POSTs to /api/repos/refresh-all: a free git-fetch + commit-fact
   re-extraction for EVERY already-ingested repository (no LLM calls; new
   commits land unanalyzed, mirroring _doBackfillEmbeddings's busy/result
   style). Always available on the home view — with zero tracked
   repositories the endpoint already returns a zeroed response
   (total_repositories: 0), so no client-side visibility gating is needed;
   that case is simply reported as "nothing to refresh" below.
   ========================================================= */
async function _doRefreshAll() {
  const btn = document.getElementById('refresh-all-btn');
  const statusEl = document.getElementById('refresh-all-status');
  if (!btn) return;
  btn.disabled = true;
  if (statusEl) {
    statusEl.textContent = 'Refreshing…';
    statusEl.style.color = 'var(--yellow)';
  }
  let res;
  try {
    res = await fetch('/api/repos/refresh-all', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
  } catch {
    if (statusEl) {
      statusEl.textContent = 'Refresh failed — check the server and try again.';
      statusEl.style.color = 'var(--red)';
    }
    btn.disabled = false;
    return;
  }
  if (!res.ok) {
    if (statusEl) {
      statusEl.textContent = `Refresh failed (HTTP ${res.status}) — try again.`;
      statusEl.style.color = 'var(--red)';
    }
    btn.disabled = false;
    return;
  }
  const data = await res.json();
  if (statusEl) {
    statusEl.textContent = data.total_repositories === 0
      ? 'Nothing to refresh yet — add a repository first.'
      : `Refreshed ${data.refreshed_count} of ${data.total_repositories} repositories · ${data.total_new_commits} new commits · ${data.failed_count} failed`;
    statusEl.style.color = data.failed_count > 0 ? 'var(--yellow)' : 'var(--green)';
  }
  btn.disabled = false;
  await loadRepos();
  renderRepoCards();
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
  const delBtn = document.getElementById('sh-delete-btn');
  if (delBtn) delBtn.style.display = 'none';
  const backfillBtn = document.getElementById('sh-backfill-btn');
  if (backfillBtn) backfillBtn.style.display = 'none';
  const stopBtn = document.getElementById('sh-analyze-stop-btn');
  if (stopBtn) stopBtn.style.display = 'none';
  if (_analyzePoll) { clearInterval(_analyzePoll); _analyzePoll = null; }
  document.querySelectorAll('.repo-item').forEach(el => el.classList.remove('active'));
  renderRepoCards();
}

function renderHeaderRepoMeta() {
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
    _loadBackfillStatus(currentRepo);
    const delBtn = document.getElementById('sh-delete-btn');
    if (delBtn) delBtn.style.display = '';
  }
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

/* =========================================================
   Embedding backfill (spec 027) — per-repo dashboard control.
   Visibility rule (LOCKED): shown only when the status endpoint reports
   available === true (an OPENAI_API_KEY is configured) AND missing > 0
   (at least one already-analyzed item still lacks an embedding). Hidden
   in every other case (no key, or nothing missing) — never an error state.
   ========================================================= */
async function _loadBackfillStatus(repoId) {
  const btn = document.getElementById('sh-backfill-btn');
  if (!btn) return;
  // Hide immediately so a stale label from a previously selected repo never
  // flashes while this repo's status is in flight.
  btn.style.display = 'none';
  let status;
  try {
    status = await apiFetch(`/api/repos/${encodeURIComponent(repoId)}/backfill-embeddings`);
  } catch {
    return; // non-critical — leave the control hidden
  }
  if (currentRepo !== repoId) return; // repo changed while the request was in flight
  if (status.available && status.missing > 0) {
    btn.textContent = `Enable semantic search (${status.missing})`;
    btn.title = `Compute embeddings for ${status.missing} already-analyzed item(s) missing them`;
    btn.disabled = false;
    btn.style.color = '';
    btn.style.display = '';
  }
}

/** Triggered by the "Enable semantic search" header button. POSTs to the
 * backfill endpoint (synchronous — the backend computes and persists
 * embeddings for every already-analyzed item missing one, then returns
 * counts directly, no polling needed). On success, shows a concise
 * embedded/already-present/failed summary, then re-checks status so the
 * button hides once nothing is missing anymore. On a 503 (no OPENAI_API_KEY)
 * or any other error, shows a non-alarming message and re-enables the
 * button rather than leaving it stuck in a busy state. */
async function _doBackfillEmbeddings() {
  if (!currentRepo) return;
  const repoId = currentRepo;
  const btn = document.getElementById('sh-backfill-btn');
  if (!btn) return;
  btn.disabled = true;
  btn.style.color = 'var(--yellow)';
  btn.textContent = 'Computing embeddings…';
  let res;
  try {
    res = await fetch(`/api/repos/${encodeURIComponent(repoId)}/backfill-embeddings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
  } catch {
    btn.textContent = 'Backfill failed — check the server and try again';
    btn.style.color = 'var(--red)';
    btn.disabled = false;
    return;
  }
  if (res.status === 503) {
    btn.textContent = 'Semantic search needs an OpenAI key';
    btn.style.color = 'var(--muted)';
    btn.disabled = true;
    return;
  }
  if (!res.ok) {
    btn.textContent = `Backfill failed (HTTP ${res.status}) — try again`;
    btn.style.color = 'var(--red)';
    btn.disabled = false;
    return;
  }
  const data = await res.json();
  btn.textContent = `Embedded ${data.embedded}, ${data.already_present} already present, ${data.failed} failed`;
  btn.style.color = 'var(--green)';
  if (currentRepo === repoId) _loadBackfillStatus(repoId);
}

async function refreshCurrentRepoMeta(repoId) {
  const data = await apiFetch('/api/repos');
  reposCache = data.repos || [];
  if (currentRepo === repoId) {
    currentRepoMeta = reposCache.find(r => r.repository_id === repoId) || currentRepoMeta;
    renderHeaderRepoMeta();
  }
}

function selectRepo(repoId) {
  if (currentRepo === repoId && document.getElementById('repo-view').classList.contains('visible')) return;
  currentRepo = repoId;
  patternsData = null;
  detailLoaded = false;
  _analyzePrefetch = null;
  clearUpdatedTabs();
  currentRepoMeta = reposCache.find(r => r.repository_id === repoId) || null;
  // Spec 029: warm the verified file-path cache so the streaming Ask tab (which
  // reads it synchronously) has it ready; loadCaseStudy also awaits the same call.
  _loadFilePathSet(repoId);

  document.querySelectorAll('.repo-item').forEach(el =>
    el.classList.toggle('active', el.dataset.id === repoId)
  );
  document.getElementById('home-view').style.display = 'none';
  document.getElementById('repo-view').classList.add('visible');
  document.getElementById('btn-tips').style.display = '';

  renderHeaderRepoMeta();
  _syncAnalyzeStatus(repoId);

  detailLoaded = true;
  switchTab('overview');
  loadTimeline(repoId);
  loadOverview(repoId);
  loadCaseStudy(repoId);
  loadPatterns(repoId);
  loadContributors(repoId);
  _resetAskTab(repoId);
}

/* =========================================================
   Timeline
   ========================================================= */
let _tlAllCommits = [];
let _tlPatterns = null;
let _tlHourFilter = null; // set when chart click drills into a specific hour
let _commitAudience = localStorage.getItem('commit-audience') || 'expert';
// Sync selector to persisted value on load (selector HTML defaults to "expert")
document.addEventListener('DOMContentLoaded', () => {
  const sel = document.getElementById('commit-audience-select');
  if (sel) sel.value = _commitAudience;
});

function _setCommitAudience(audience) {
  _commitAudience = audience;
  localStorage.setItem('commit-audience', audience);
  const sel = document.getElementById('commit-audience-select');
  if (sel) sel.value = audience;
  _applyTimelineFilters();
  _updateAudienceBanner(audience);
}

function _updateAudienceBanner(audience) {
  const banner = document.getElementById('tl-audience-banner');
  if (!banner || !_tlAllCommits?.length) return;
  const field = audience === 'beginner' ? 'summary_beginner' : 'summary_expert';
  const hasAny = _tlAllCommits.some(c => c[field] != null && c[field] !== '');
  if (!hasAny) {
    const label = audience === 'beginner' ? 'Beginner' : 'Expert';
    banner.innerHTML = `<span>${label} summaries haven't been generated yet — these commits were analyzed before dual-audience support.</span>
      <span>Use <strong>+ Analyze</strong> to re-analyze and generate them.</span>`;
    banner.style.display = 'flex';
  } else {
    banner.style.display = 'none';
    banner.innerHTML = '';
  }
}

/* Commits-tab category multi-select: mirrors the donut's own multi-select
 * (spec 018) — same toggleSelection()/catColor()/catTipKey() helpers, same
 * selected/dimmed chip styling — so a category reads the same color/shape
 * whether toggled from the donut legend or from here. Reset per repo load
 * in loadTimeline(), not on every filter application. */
/* Matches CommitCategory (domain/analysis.py) exactly. The old single-select
 * only listed 7 of these 10 (plus a bogus "OTHER" that matched nothing) —
 * SECURITY/PERFORMANCE/CHORE/UNKNOWN commits had no filter option at all.
 * Fixed here since this list was being rebuilt anyway. */
const _COMMIT_CATEGORIES = [
  'FEATURE', 'BUGFIX', 'REFACTOR', 'TEST', 'DOCS', 'BUILD',
  'SECURITY', 'PERFORMANCE', 'CHORE', 'UNKNOWN',
];
let _commitsCategorySelected = new Set();

function _renderCommitsCategoryChips() {
  const el = document.getElementById('commits-cat-chips');
  if (!el) return;
  el.innerHTML = _COMMIT_CATEGORIES.map(cat => {
    const isSelected = _commitsCategorySelected.has(cat);
    const isDimmed = _commitsCategorySelected.size > 0 && !isSelected;
    const cls = ['donut-legend-item', isSelected ? 'selected' : '', isDimmed ? 'dimmed' : ''].filter(Boolean).join(' ');
    return `<span class="${cls}" data-tip="${catTipKey(cat)}" data-tip-suffix="(Click to toggle)" tabindex="0" role="listitem" aria-pressed="${isSelected}"
      style="cursor:pointer"
      onclick="_toggleCommitsCategory('${cat}')"
      onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();this.click()}">
      <span class="donut-legend-dot" style="background:${catColor(cat)}" aria-hidden="true"></span>
      ${cat.toLowerCase()}
    </span>`;
  }).join('');
}

window._toggleCommitsCategory = function(cat) {
  _commitsCategorySelected = toggleSelection(_commitsCategorySelected, cat.toUpperCase());
  _renderCommitsCategoryChips();
  _applyTimelineFilters();
};

/** Cross-link from a donut *slice* click (legend clicks keep toggling the
 * donut's own local multi-select, unchanged) — drills into the Commits tab
 * filtered to that one category, mirroring _filterByEvidenceShas'/spec 017's
 * hour-click cross-link style (switchTab, ensure _tlAllCommits is loaded,
 * apply the filter with a labeled description). */
window._drillDonutCategoryToCommits = function(cat) {
  if (!cat || !currentRepo) return;
  const upper = cat.toUpperCase();
  switchTab('commits');
  setTimeout(async () => {
    if (!_tlAllCommits.length) await loadTimeline(currentRepo);
    _commitsCategorySelected = new Set([upper]);
    _renderCommitsCategoryChips();
    _applyCommitFilter(`Category: ${upper}`);
  }, 100);
};

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
  let commits = _tlAllCommits.slice(0, limitN);
  if (_tlHourFilter) {
    // Match using the same normalization as buildActivityData: slice(0,13).replace('T',' ')
    commits = commits.filter(c =>
      (c.committed_at || '').slice(0, 13).replace('T', ' ') === _tlHourFilter.hourPrefix
    );
  } else {
    if (fromDate) commits = commits.filter(c => (c.committed_at || '') >= fromDate);
    if (toDate) commits = commits.filter(c => (c.committed_at || '') <= toDate + 'T23:59:59');
  }
  if (keyword) {
    commits = commits.filter(c =>
      (c.message||'').toLowerCase().includes(keyword) ||
      (c.author_name||'').toLowerCase().includes(keyword) ||
      (c.sha||'').toLowerCase().startsWith(keyword) ||
      (c.category||'').toLowerCase().includes(keyword) ||
      (c.summary||'').toLowerCase().includes(keyword)
    );
  }
  if (_commitsCategorySelected.size > 0) {
    commits = commits.filter(c => _commitsCategorySelected.has((c.category || '').toUpperCase()));
  }
  if (_evidenceShaFilter) commits = commits.filter(c => _evidenceShaFilter.has(c.sha));
  // A narrowing search/filter is active (as opposed to just the commit-count limit) —
  // expand day groups automatically so matches aren't hidden behind a closed day.
  const cat = _commitsCategorySelected.size > 0 ? Array.from(_commitsCategorySelected).join(', ') : '';
  const hasActiveFilter = !!(keyword || fromDate || toDate || cat || _evidenceShaFilter || _tlHourFilter);
  _updateCommitFilterBar({ hasActiveFilter, keyword, fromDate, toDate, cat });
  renderTimeline(commits, _tlPatterns, { defaultOpen: hasActiveFilter });
}

/** Show/hide the "Clear filters" bar above the Commits timeline and, unless a
 * caller already set a more specific label via _applyCommitFilter (evidence
 * or hotspot drill-downs), describe which manual filter(s) are active. */
function _updateCommitFilterBar({ hasActiveFilter, keyword, fromDate, toDate, cat }) {
  const bar = document.getElementById('commits-filter-bar');
  const descEl = document.getElementById('commits-filter-desc');
  if (bar) bar.style.display = hasActiveFilter ? 'flex' : 'none';
  if (!descEl || !hasActiveFilter) return;
  // Evidence/hotspot-driven filters already set a specific label — keep it.
  if (_evidenceShaFilter) return;
  const parts = [];
  if (cat) parts.push(`Category: ${cat}`);
  if (keyword) parts.push(`Search: "${keyword}"`);
  if (_tlHourFilter) parts.push('Time period selected');
  else if (fromDate || toDate) parts.push(`Date: ${fromDate || '…'} – ${toDate || '…'}`);
  descEl.textContent = parts.join(' · ');
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
    _commitsCategorySelected = new Set();
    _renderCommitsCategoryChips();
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

function renderTimeline(commits, patterns, { defaultOpen = false } = {}) {
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
      <span style="color:var(--muted)">·</span> <strong>${commits.length}</strong> shown
      ${mergeCommits > 0 ? `<span style="color:var(--muted)">·</span> <span data-tip="tlMerge" tabindex="0" style="color:var(--muted)">↔ ${mergeCommits} merge${mergeCommits !== 1 ? 's' : ''}</span>` : ''}
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

    // Group this month's commits by day so each day can collapse/expand as a unit.
    const dayGroups = [];
    monthCommits.forEach(c => {
      const dayKey = (c.committed_at || '').slice(0, 10);
      const last = dayGroups[dayGroups.length - 1];
      if (!last || last.day !== dayKey) dayGroups.push({ day: dayKey, commits: [] });
      dayGroups[dayGroups.length - 1].commits.push(c);
    });

    dayGroups.forEach((group, di) => {
      const dayId = `tlday-${month.replace('-', '')}-${di}`;
      const [dyear, dmon, dday] = group.day.split('-');
      const dayLabel = new Date(parseInt(dyear), parseInt(dmon) - 1, parseInt(dday))
        .toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      const openNow = defaultOpen;
      html += `<div class="tl-day-sep" id="tlsep-${dayId}" role="button" tabindex="0"
          aria-expanded="${openNow ? 'true' : 'false'}" aria-controls="${dayId}"
          onclick="tlDayToggle('${dayId}')"
          onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();tlDayToggle('${dayId}')}">
        <span class="tl-day-chevron" aria-hidden="true">›</span>${esc(dayLabel)}
        <span class="tl-day-count">${group.commits.length} commit${group.commits.length !== 1 ? 's' : ''}</span>
      </div>`;
      html += `<div class="tl-day-group${openNow ? ' open' : ''}" id="${dayId}">`;

      group.commits.forEach((c, i) => {
        const xid = `tlx-${month.replace('-', '')}-${di}-${i}`;
        const cat = (c.category || '').toUpperCase();
        // Resolve audience-aware summary: use dual fields when available, fall back to legacy summary
        const hasDualAudience = c.summary_beginner !== undefined && c.summary_beginner !== null;
        const activeSummary = hasDualAudience
          ? (_commitAudience === 'beginner' ? c.summary_beginner : (c.summary_expert ?? ''))
          : (c.summary || '');
        const hasAnalysis = !!(c.category || activeSummary);
        const shaUrl = currentRepoMeta?.canonical_url?.includes('github.com')
          ? `${currentRepoMeta.canonical_url}/commit/${c.sha || ''}`
          : null;
        // All commits with a GitHub link or a meaningful summary are expandable
        const hasDetail = !!(activeSummary && activeSummary !== c.message) || !!shaUrl;

        const interactiveAttrs = hasDetail
          ? `onclick="tlToggle('${xid}')" role="button" tabindex="0" aria-expanded="false"
                 onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();tlToggle('${xid}')}">`
          : '>';
        html += `<div class="tl-row${hasAnalysis ? ' analyzed' : ''}" id="tlr-${xid}" ${interactiveAttrs}
          <span class="tl-date">${esc(fmtMonthDay(c.committed_at || ''))}</span>
          <span class="tl-msg">${esc(truncate(c.message || '', 70))}</span>
          <div class="tl-badges">
            ${cat ? `<span class="badge ${badgeClass(c.category || '')}" data-tip="${catTipKey(c.category || '')}">${esc(cat)}</span>` : ''}
            ${hasDetail ? '<span class="tl-expand-arrow" aria-hidden="true">›</span>' : ''}
          </div>
        </div>`;
        if (hasDetail) {
          const sha7 = (c.sha || '').slice(0, 7);
          const shaEl = shaUrl
            ? `<a href="${esc(shaUrl)}" target="_blank" rel="noopener" style="margin-left:.5rem;font-family:monospace;font-size:10px;color:var(--muted)">${esc(sha7)}</a>`
            : `<span style="margin-left:.5rem;font-family:monospace;font-size:10px;color:var(--muted)">${esc(sha7)}</span>`;
          const legacyNote = hasDualAudience ? '' : `<span class="tl-legacy-note" data-tip="tlLegacySummary" style="display:inline-block;margin-left:.5rem;font-size:11px;color:var(--muted);cursor:help">(single-summary analysis)</span>`;
          html += `<div class="tl-detail" id="${xid}">
            ${esc(activeSummary)}${legacyNote}
            ${shaEl}
          </div>`;
        }
      });
      html += '</div>';
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

function tlDayToggle(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle('open');
  const sep = document.getElementById('tlsep-' + id);
  if (sep) sep.setAttribute('aria-expanded', el.classList.contains('open') ? 'true' : 'false');
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
  clearUpdatedTab(tabName);
}
document.querySelectorAll('.tab-btn').forEach(btn =>
  btn.addEventListener('click', () => {
    if (btn.dataset.tab === 'commits') _clearCommitFilters();
    switchTab(btn.dataset.tab);
  })
);

function markUpdatedTabs(tabIds) {
  tabIds.forEach(tabId => {
    if (UPDATED_ANALYSIS_TABS.has(tabId)) _updatedTabs.add(tabId);
  });
  renderUpdatedTabIndicators();
}

function clearUpdatedTab(tabId) {
  if (!_updatedTabs.delete(tabId)) return;
  renderUpdatedTabIndicators();
}

function clearUpdatedTabs() {
  _updatedTabs = new Set();
  renderUpdatedTabIndicators();
}

function renderUpdatedTabIndicators() {
  document.querySelectorAll('.tab-btn[data-tab]').forEach(btn => {
    const isUpdated = _updatedTabs.has(btn.dataset.tab);
    const label = btn.dataset.label || btn.textContent.trim();
    btn.dataset.label = label;
    btn.classList.toggle('is-updated', isUpdated);
    btn.setAttribute('aria-label', isUpdated ? `${label} updated after analysis` : label);
    if (isUpdated) btn.title = `${label} updated after analysis`;
    else btn.removeAttribute('title');
  });
}

/* =========================================================
   Overview
   ========================================================= */
/* Activity chart zoom-ladder state (spec 017): current scale and -- when the
 * user has drilled into a column -- the calendar span that scopes the chart.
 * Reset to an auto-picked scale (bestScale) with no span every time a repo's
 * Overview is (re)loaded. Persists across the activity-date-from/to date-box
 * filter, which narrows the commit set the zoom operates on rather than
 * resetting the zoom (see spec 017 Domain concepts). */
let _actScale = null;
let _actSpan = null;

/* Commit-categories donut multi-select (spec 018): categories currently
 * toggled into the donut's selection (upper-cased, e.g. "BUGFIX"). Empty
 * means "show all" (the default). Reset to a new empty Set every time a
 * repo's Overview is (re)loaded -- same lifecycle as _actScale/_actSpan. */
let _donutSelected = new Set();

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

  let overviewIntroHtml = '';
  if (caseStudy?.narrative) {
    const lines = caseStudy.narrative.split('\n');
    const introLines = [];
    let inFirstSection = false;
    let firstSectionFound = false;
    for (const line of lines) {
      if (/^#\s/.test(line)) continue;
      if (/^##\s/.test(line) && !firstSectionFound) { firstSectionFound = true; inFirstSection = true; continue; }
      if (/^##\s/.test(line) && firstSectionFound) break;
      if (inFirstSection || !firstSectionFound) introLines.push(line);
    }
    const introText = introLines.join('\n').trim();
    if (introText) {
      // Show only the first paragraph, capped to 2 sentences — full narrative is in Case Study
      const firstPara = (introText.split(/\n\n+/)[0] || introText).trim();
      const sentences = firstPara.split(/(?<=[.!?])\s+/);
      const capped = sentences.slice(0, 2).join(' ');
      const rendered = renderMarkdown(capped, 'p');
      overviewIntroHtml = `<div class="overview-intro">${rendered}<p style="margin-top:0.5rem"><a class="overview-cs-link" onclick="switchTab('case-study')" tabindex="0" role="button" onkeydown="if(event.key==='Enter')switchTab('case-study')">Read full case study →</a></p></div>`;
    }
  }

  el.innerHTML = `${overviewIntroHtml}
    <div class="charts-row">
      <div class="chart-box">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:0.5rem;margin-bottom:0.75rem">
          <h3 style="margin:0">Commit Categories</h3>
          <button id="donut-clear-selection" onclick="_clearDonutSelection()" title="Clear category selection"
            aria-label="Clear category selection and show all categories"
            style="display:none;padding:0.2rem 0.5rem;border:1px solid var(--border);border-radius:4px;background:var(--surface);color:var(--muted);font-size:11px;cursor:pointer;font-family:inherit">Clear</button>
        </div>
        <div class="chart-container" style="height:170px"><canvas id="chart-donut" aria-label="Donut chart showing commit category distribution. Click a slice to view its commits in the Commits tab."></canvas></div>
        <div id="donut-legend-custom" class="donut-legend" role="list" aria-label="Category legend"></div>
      </div>
      <div class="chart-box">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:0.5rem;margin-bottom:0.4rem;flex-wrap:wrap">
          <h3 style="margin:0">Commit Activity</h3>
          <div style="display:flex;gap:0.35rem;align-items:center;flex-wrap:wrap">
            <div style="display:flex;gap:0.2rem;align-items:center" role="group" aria-label="Activity chart zoom">
              <button id="activity-scale-coarser" onclick="_activityScaleCoarser()" title="Zoom out (coarser)"
                aria-label="Zoom out to a coarser time scale"
                style="padding:0.2rem 0.5rem;border:1px solid var(--border);border-radius:4px;background:var(--surface);color:var(--muted);font-size:11px;cursor:pointer;font-family:inherit">−</button>
              <span id="activity-scale-label" style="font-size:10px;color:var(--muted);min-width:44px;text-align:center;text-transform:capitalize"></span>
              <button id="activity-scale-finer" onclick="_activityScaleFiner()" title="Zoom in (finer)"
                aria-label="Zoom in to a finer time scale"
                style="padding:0.2rem 0.5rem;border:1px solid var(--border);border-radius:4px;background:var(--surface);color:var(--muted);font-size:11px;cursor:pointer;font-family:inherit">+</button>
              <button id="activity-scale-reset" onclick="_activityResetZoom()" title="Reset zoom to the full range"
                aria-label="Reset zoom to the full range"
                style="display:none;padding:0.2rem 0.5rem;border:1px solid var(--border);border-radius:4px;background:var(--surface);color:var(--muted);font-size:11px;cursor:pointer;font-family:inherit">⤢</button>
            </div>
            <input type="date" id="activity-date-from" aria-label="Activity chart from date"
              style="padding:0.2rem 0.4rem;border:1px solid var(--border);border-radius:4px;background:var(--surface);color:var(--text);font-size:11px;font-family:inherit;color-scheme:dark"
              oninput="_rebuildActivityChart()" title="From date">
            <span style="color:var(--muted);font-size:11px">–</span>
            <input type="date" id="activity-date-to" aria-label="Activity chart to date"
              style="padding:0.2rem 0.4rem;border:1px solid var(--border);border-radius:4px;background:var(--surface);color:var(--text);font-size:11px;font-family:inherit;color-scheme:dark"
              oninput="_rebuildActivityChart()" title="To date">
            <button onclick="_clearActivityDateFilter()" title="Clear date range"
              style="padding:0.2rem 0.5rem;border:1px solid var(--border);border-radius:4px;background:var(--surface);color:var(--muted);font-size:11px;cursor:pointer;font-family:inherit">×</button>
          </div>
        </div>
        <div class="chart-container" id="chart-activity-container" style="height:220px"><canvas id="chart-activity" aria-label="Bar chart showing commit activity over time"></canvas></div>
      </div>
    </div>
    <div class="chart-box" style="margin-bottom:1rem">
      <h3>Top Hotspot Files <span style="font-size:10px;font-weight:400;color:var(--muted);text-transform:none">(click to filter commits)</span></h3>
      <div class="chart-container" style="height:${Math.max(120, Math.min(hotspots.slice(0,5).length, 5) * 36)}px">
        <canvas id="chart-hotspots" aria-label="Horizontal bar chart showing top hotspot files by commit count"></canvas>
      </div>
    </div>`;

  const _tc = () => getComputedStyle(document.documentElement).getPropertyValue('--muted').trim() || '#94a3b8';
  const _tcy = () => getComputedStyle(document.documentElement).getPropertyValue('--text').trim() || '#e2e8f0';
  const _gc = () => getComputedStyle(document.documentElement).getPropertyValue('--border').trim() || '#2d3148';

  /* Commit-categories donut multi-select (spec 018): _donutSelected drives
   * both the rendered slices (visibleCategories) and the legend's
   * selected/dimmed styling. Reset per-load below, alongside _actScale/
   * _actSpan. Legend clicks toggle _donutSelected via _toggleDonutCategory().
   * Slice clicks instead drill into the Commits tab for that one category
   * (_drillDonutCategoryToCommits) — deliberately decoupled from the legend
   * so "click the chart to see specifics" matches the Activity chart's own
   * drill convention (spec 017), while the legend stays a same-tab compare. */
  function _rebuildDonutChart() {
    const visible = visibleCategories(catCounts, _donutSelected);
    destroyChart('donut');
    if (visible.length === 0) {
      document.getElementById('chart-donut').parentElement.innerHTML = '<div class="empty-state" style="padding:1rem">No category data</div>';
      _updateDonutLegend();
      return;
    }
    _charts['donut'] = new Chart(document.getElementById('chart-donut'), {
      type: 'doughnut',
      data: { labels: visible.map(c => c.category), datasets: [{ data: visible.map(c => c.count), backgroundColor: visible.map(c => catColor(c.category)), borderWidth: 1, borderColor: '#0f1117' }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { footer: () => 'Click to view commits for this category' } },
        },
        onClick(evt, els) {
          if (!els.length) return;
          const cat = visible[els[0].index]?.category;
          if (!cat) return;
          window._drillDonutCategoryToCommits(cat);
        },
      },
    });
    _updateDonutLegend();
  }

  function _updateDonutLegend() {
    const legendEl = document.getElementById('donut-legend-custom');
    if (legendEl) legendEl.innerHTML = catCounts.map(c => {
      const upper = (c.category || '').toUpperCase();
      const isSelected = _donutSelected.has(upper);
      const isDimmed = _donutSelected.size > 0 && !isSelected;
      const cls = ['donut-legend-item', isSelected ? 'selected' : '', isDimmed ? 'dimmed' : ''].filter(Boolean).join(' ');
      return `<span class="${cls}" data-tip="${catTipKey(c.category)}" data-tip-suffix="(Click to toggle)" tabindex="0" role="listitem" aria-pressed="${isSelected}"
        style="cursor:pointer"
        onclick="_toggleDonutCategory('${esc(c.category)}')"
        onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();this.click()}">
        <span class="donut-legend-dot" style="background:${catColor(c.category)}" aria-hidden="true"></span>
        ${esc(c.category.toLowerCase())}
      </span>`;
    }).join('');
    const clearBtn = document.getElementById('donut-clear-selection');
    if (clearBtn) clearBtn.style.display = _donutSelected.size > 0 ? 'inline-flex' : 'none';
  }

  window._toggleDonutCategory = function(cat) {
    if (!cat) return;
    _donutSelected = toggleSelection(_donutSelected, cat.toUpperCase());
    _rebuildDonutChart();
  };

  window._clearDonutSelection = function() {
    _donutSelected = new Set();
    _rebuildDonutChart();
  };

  _donutSelected = new Set();
  if (catCounts.length > 0) {
    _rebuildDonutChart();
  } else {
    document.getElementById('chart-donut').parentElement.innerHTML = '<div class="empty-state" style="padding:1rem">No category data</div>';
  }

  const commitList = commits.commits || [];
  window._activityAllCommits = commitList;

  function _buildActivityChart(filteredCommits) {
    if (!_actScale) _actScale = bestScale(filteredCommits);
    _updateActivityScaleControls();
    const { labels: actLabels, data: actData } = buildActivityData(filteredCommits, _actScale);
    const container = document.getElementById('chart-activity-container');
    if (!actLabels.length) {
      destroyChart('activity');
      if (container) {
        container.innerHTML = `<div class="tl-empty">
          <p>No analyzed commits yet.</p>
          <p style="margin-top:.5rem">Use the <strong>+ Analyze</strong> button above to start commit analysis.</p>
        </div>`;
      }
      return;
    }
    if (container && !document.getElementById('chart-activity')) {
      container.innerHTML = '<canvas id="chart-activity" aria-label="Bar chart showing commit activity over time"></canvas>';
    }
    destroyChart('activity');
    const isFinestScale = _actScale === 'hour';
    _charts['activity'] = new Chart(document.getElementById('chart-activity'), {
      type: 'bar',
      data: { labels: actLabels, datasets: [{ label: 'Commits', data: actData, backgroundColor: '#6366f1', borderRadius: 3 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { footer: () => isFinestScale ? 'Click to view in Commits' : 'Click to zoom in' } },
        },
        scales: { x: { ticks: { color: _tc(), font: { size: 10 }, maxRotation: 45 }, grid: { color: _gc() } }, y: { ticks: { color: _tc(), font: { size: 10 } }, grid: { color: _gc() } } },
        onClick(evt, els) {
          if (!els.length) return;
          const key = actLabels[els[0].index];
          if (!key) return;
          if (_actScale === 'hour') {
            // Finest scale: no finer drill exists, so keep the pre-existing
            // behavior of cross-linking to the Commits tab filtered to this
            // specific hour (spec 017 AC-05).
            switchTab('commits');
            setTimeout(() => {
              const day = key.slice(0, 10);
              // hourPrefix matches what bucketKey('hour') / _applyTimelineFilters
              // use as the key prefix: "YYYY-MM-DD HH"
              _tlHourFilter = { hourPrefix: key.slice(0, 13) };
              const fromEl = document.getElementById('tl-date-from');
              const toEl = document.getElementById('tl-date-to');
              if (fromEl) fromEl.value = day;
              if (toEl) toEl.value = day;
              _applyTimelineFilters();
            }, 300);
            return;
          }
          // All other scales: drill one level finer within the chart itself
          // (spec 017 AC-04) instead of jumping to the Commits tab.
          const finer = scaleFiner(_actScale);
          if (!finer) return;
          _actSpan = spanForColumn(key, _actScale);
          _actScale = finer;
          _rebuildActivityChartAtScale();
        },
      },
    });
  }

  function _activityFilteredCommits() {
    const from = document.getElementById('activity-date-from')?.value;
    const to = document.getElementById('activity-date-to')?.value;
    let commits = window._activityAllCommits || [];
    if (from) commits = commits.filter(c => (c.committed_at || '') >= from);
    if (to) commits = commits.filter(c => (c.committed_at || '') <= to + 'T23:59:59');
    return commitsInSpan(commits, _actSpan);
  }

  function _rebuildActivityChartAtScale() {
    _buildActivityChart(_activityFilteredCommits());
  }

  function _updateActivityScaleControls() {
    const coarserBtn = document.getElementById('activity-scale-coarser');
    const finerBtn = document.getElementById('activity-scale-finer');
    const label = document.getElementById('activity-scale-label');
    const resetBtn = document.getElementById('activity-scale-reset');
    if (coarserBtn) coarserBtn.disabled = !scaleCoarser(_actScale);
    if (finerBtn) finerBtn.disabled = !scaleFiner(_actScale);
    if (label) label.textContent = _actScale ? _actScale.charAt(0).toUpperCase() + _actScale.slice(1) : '';
    if (resetBtn) resetBtn.style.display = _actSpan ? 'inline-flex' : 'none';
  }

  window._rebuildActivityChart = function() {
    _buildActivityChart(_activityFilteredCommits());
  };

  window._clearActivityDateFilter = function() {
    const f = document.getElementById('activity-date-from');
    const t = document.getElementById('activity-date-to');
    if (f) f.value = '';
    if (t) t.value = '';
    _buildActivityChart(commitsInSpan(window._activityAllCommits || [], _actSpan));
  };

  window._activityScaleCoarser = function() {
    const coarser = scaleCoarser(_actScale);
    if (!coarser) return;
    _actSpan = _actSpan ? alignSpanToScale(_actSpan, coarser) : null;
    _actScale = coarser;
    _rebuildActivityChartAtScale();
  };

  window._activityScaleFiner = function() {
    const finer = scaleFiner(_actScale);
    if (!finer) return;
    _actScale = finer;
    _rebuildActivityChartAtScale();
  };

  window._activityResetZoom = function() {
    _actSpan = null;
    _actScale = bestScale(window._activityAllCommits || []);
    _rebuildActivityChartAtScale();
  };

  _actScale = bestScale(commitList);
  _actSpan = null;
  _buildActivityChart(commitList);

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

function _renderSectionCards(content, sectionTitle) {
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
    const html = renderMarkdown(content);
    return `<div class="markdown-body">${html}</div>`;
  }

  return cards.map((card, i) => {
    const cleanTitle = card.title.replace(/\*\*/g, '').replace(/^#+\s*/, '').trim();
    // Fix 5: Detect architectural pattern section for special styling.
    // Batch 156, bug 4: scoped out of 'Engineering Lessons' so a lesson title like
    // "Streaming Changes the Architecture..." isn't wrongly highlighted as a pattern card.
    const isArchPattern = sectionTitle !== 'Engineering Lessons'
      && /architect|key pattern|design pattern|structural pattern/i.test(cleanTitle);
    const icon = isArchPattern ? '🏛' : _iconForHeading(cleanTitle);
    const body = card.lines.join('\n').trim();
    const html = renderMarkdown(body);
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
    return `<div class="markdown-body">${renderMarkdown(content)}</div>`;
  }

  // Partition commits by dates extracted from phase titles, falling back to equal buckets
  const sorted = (_tlAllCommits || []).slice().sort((a,b) => (a.committed_at||'') < (b.committed_at||'') ? -1 : 1);
  const total = sorted.length;

  // Try to extract an anchor date from each phase title (and first content lines)
  const anchors = phases.map(p =>
    _extractIsoDate(p.title) || _extractIsoDate(p.lines.slice(0, 6).join(' ')) || null
  );
  const hasAnchors = anchors.some(a => a !== null);

  const perPhase = hasAnchors ? 0 : (phases.length ? Math.ceil(total / phases.length) : 0);
  const buckets = phases.map((p, idx) => {
    let slice;
    if (hasAnchors) {
      const from = anchors[idx];
      let to = null;
      for (let j = idx + 1; j < anchors.length; j++) { if (anchors[j]) { to = anchors[j]; break; } }
      if (from) {
        slice = sorted.filter(c => {
          const d = (c.committed_at || '').slice(0, 10);
          return d >= from && (to ? d < to : true);
        });
      } else {
        // Phase with no anchor: grab what falls between the previous and next anchors
        const prev = anchors.slice(0, idx).reverse().find(a => a);
        slice = sorted.filter(c => {
          const d = (c.committed_at || '').slice(0, 10);
          return (prev ? d >= prev : true) && (to ? d < to : true);
        });
      }
    } else {
      slice = sorted.slice(idx * perPhase, (idx + 1) * perPhase);
    }
    return {
      dateRange: slice.length >= 2
        ? `${slice[0].committed_at.slice(0,10)} → ${slice[slice.length-1].committed_at.slice(0,10)}`
        : slice.length === 1 ? slice[0].committed_at.slice(0,10) : '',
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
    const md = renderMarkdown(bodyRaw);
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
  const wasOpen = card.classList.contains('open');
  card.classList.toggle('open');
  if (!wasOpen) card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
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
    return `<div class="markdown-body">${renderMarkdown(content)}</div>`;
  }
  return cards.map((card, i) => {
    const body = card.lines.join('\n');
    const rest = renderMarkdown(body);
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
  // Only linkify hex in text BETWEEN tags — never inside a tag or its attributes
  // (e.g. a timeline node's title="…c0dab29…"). A blind whole-string replace would
  // inject an <a> into the attribute value and corrupt the markup.
  return html.replace(/<[^>]*>|[^<]+/g, (segment) => {
    if (segment.charAt(0) === '<') return segment; // a tag — leave attributes untouched
    return segment.replace(/\b([0-9a-f]{7,40})\b/gi, (match, sha) => {
      const ghUrl = `${canonicalUrl}/commit/${sha}`;
      return `<a href="${ghUrl}" target="_blank" rel="noopener" title="View commit ${sha} on GitHub" style="font-family:monospace;color:var(--text);text-decoration:underline">${sha}</a>`;
    });
  });
}

// Spec 020: file/folder path linking — safe charset shared by branch names and
// path segments alike. Only alnum, '.', '_', '/', '-' are ever considered
// safe; anything else (whitespace, quotes, control chars, URL schemes) is
// rejected rather than escaped, since these strings are untrusted (LLM
// narrative text / repository content per CODEX.md).
const _PATH_SAFE_CHARSET = /^[A-Za-z0-9._/-]+$/;

function _isSafePathLikeString(text) {
  if (!text) return false;
  if (/\s/.test(text)) return false;
  if (!_PATH_SAFE_CHARSET.test(text)) return false;
  if (text.includes('..')) return false;
  if (text.startsWith('/')) return false;
  if (text.includes('://')) return false;
  return true;
}

/** Predicate: is this backtick code-span text plausibly a repo file/folder path?
 * Conservative on purpose (spec 020 locked decision): only backtick-wrapped
 * spans are ever considered — no free-text path detection. */
function isLinkablePath(text) {
  if (!_isSafePathLikeString(text)) return false;
  // Only link real relative paths (containing a separator). A bare basename like
  // `ports.py` cannot be located in the repo tree — linking it to /blob/<branch>/ports.py
  // 404s when the file is nested. Conservative per spec 020.
  return text.includes('/');
}

/** Spec 029: verify a candidate path span against the repository's verified
 * file-path Set (the tree captured from `git ls-tree`). Returns 'file' when the
 * span is an EXACT tree member, 'folder' when it is a strict directory prefix of
 * at least one member (a trailing-slash span like `tests/` uses that prefix
 * directly), or null when unverified — an unverified span stays plain <code>, so
 * we never emit a broken link (spec 029 AC-06). */
function _verifyTreePath(text, filePathSet) {
  if (filePathSet.has(text)) return 'file';
  const prefix = text.endsWith('/') ? text : `${text}/`;
  for (const member of filePathSet) {
    if (member.startsWith(prefix)) return 'folder';
  }
  return null;
}

/** Visible link text: the basename (last non-empty path segment). A trailing
 * slash is preserved so a folder span like `tests/` still reads as `tests/`,
 * while `.../ports.py` reads as `ports.py` (spec 029 §8). */
function _pathBasename(path) {
  const segments = path.split('/').filter(segment => segment.length > 0);
  const last = segments.length ? segments[segments.length - 1] : path;
  return path.endsWith('/') ? `${last}/` : last;
}

/** Builds a GitHub blob/tree URL for a tree-verified path. `kind` comes from
 * _verifyTreePath ('file' -> blob, 'folder' -> tree); the caller must have
 * checked isLinkablePath(path) and that branch is safe. */
function _pathToGithubUrl(path, canonicalUrl, branch, kind) {
  const segment = kind === 'folder' ? 'tree' : 'blob';
  let encodedPath = path
    .split('/')
    .filter(part => part.length > 0)
    .map(encodeURIComponent)
    .join('/');
  if (path.endsWith('/')) encodedPath += '/';
  return `${canonicalUrl}/${segment}/${encodeURIComponent(branch)}/${encodedPath}`;
}

/** Spec 032: build a `basename -> full path` index from the verified tree, once per
 * _linkifyPaths call. Only basenames containing a '.' (extensioned files) are indexed,
 * so tool/function names (`manage_mcp`) and bare folder words (`interfaces`) are never
 * basename-resolved. A basename shared by two-or-more members maps to `null` (the
 * ambiguity sentinel) — ambiguous basenames never link (spec 032 AC-02/AC-04/AC-08). */
function _basenameIndex(filePathSet) {
  const index = new Map();
  for (const member of filePathSet) {
    const base = member.split('/').pop();
    if (!base || !base.includes('.')) continue;
    if (index.has(base)) {
      index.set(base, null); // seen on a second member => ambiguous
    } else {
      index.set(base, member);
    }
  }
  return index;
}

/** Spec 032: resolve a bare basename span (no '/') to its unique full path via the
 * basename index. Returns null for a slashed span (handled by the spec-029 branch), an
 * unknown basename (zero members), or an ambiguous one (the null sentinel) —
 * spec 032 AC-01/AC-02/AC-03. */
function _resolveUniqueBasename(text, basenameIndex) {
  if (text.includes('/')) return null;
  const resolved = basenameIndex.get(text);
  return typeof resolved === 'string' ? resolved : null;
}

/** Spec 020: rewrite backtick-wrapped, path-plausible inline <code> spans into
 * links to the file/folder on GitHub. Must run AFTER _linkifyCommitShas on the
 * same HTML (see spec 020 Security considerations) — running it first would
 * let the SHA-linkifier's bare-hex regex match visible text nested inside an
 * already-built <a href="...blob...">, producing a broken nested anchor.
 * Running SHA-linking first means any code span the SHA pass already turned
 * into a link contains a nested <a> tag, so this pass's `[^<]*` content-purity
 * match naturally skips it — no double-processing, no corruption.
 *
 * Only bare `<code>` spans are matched (marked.js renders fenced blocks as
 * `<pre><code ...>`), and the `(?<!<pre>)` guard excludes the one case where a
 * fenced block with no language hint would otherwise look identical
 * (`<pre><code>...</code></pre>`).
 *
 * Spec 029: `filePathSet` is the repository's verified file-path Set (from
 * GET /api/repos/{id}/file-paths). A span links ONLY when it (a) still passes
 * isLinkablePath AND (b) is tree-verified by _verifyTreePath (exact member =>
 * file/blob, directory prefix of a member => folder/tree). Unverified spans stay
 * plain <code> — never a broken link. The visible text is shortened to the
 * basename and the full path goes in title= (both escaped via esc()). If the
 * set is empty/absent, or the branch/URL are unusable, the html is returned
 * unchanged (AC-07). */
function _linkifyPaths(html, canonicalUrl, defaultBranch, filePathSet) {
  if (!canonicalUrl || !canonicalUrl.includes('github.com')) return html;
  if (!defaultBranch || !_isSafePathLikeString(defaultBranch)) return html;
  if (!filePathSet || filePathSet.size === 0) return html;
  // Spec 032: build the basename -> full-path index ONCE per call (not per span).
  const basenameIndex = _basenameIndex(filePathSet);
  return html.replace(/(?<!<pre>)<code>([^<]*)<\/code>/g, (match, text) => {
    if (!_isSafePathLikeString(text)) return match;
    let kind;
    let linkPath;
    if (isLinkablePath(text)) {
      // Spec 029: a slashed span must be tree-verified (exact member => file/blob,
      // directory prefix => folder/tree); unverified spans stay plain <code>.
      kind = _verifyTreePath(text, filePathSet);
      if (!kind) return match;
      linkPath = text;
    } else {
      // Spec 032: a bare basename (no slash) links only when it resolves to a single
      // verified tree member; ambiguous or unknown basenames stay plain <code>.
      linkPath = _resolveUniqueBasename(text, basenameIndex);
      if (!linkPath) return match;
      kind = 'file';
    }
    // Defense in depth (spec 029 §12 / spec 032 §12): the RESOLVED tree path — never the
    // raw span — feeds the URL and the visible text; re-validate the safe charset before
    // it is interpolated, even though the tree set was already charset-filtered server-side.
    if (!_isSafePathLikeString(linkPath)) return match;
    const url = _pathToGithubUrl(linkPath, canonicalUrl, defaultBranch, kind);
    return `<a href="${url}" target="_blank" rel="noopener" title="${esc(linkPath)}" style="font-family:monospace">${esc(_pathBasename(linkPath))}</a>`;
  });
}

/** Reuses the same spec-020 SHA/path linkifiers for Ask tab answers, sourced
 * from currentRepoMeta (already trusted, already loaded for the open repo —
 * never taken from the LLM's own text). Ordering (SHA before path) matches
 * _linkifyPaths' own doc comment. */
function _linkifyAskAnswerHtml(html) {
  const canonicalUrl = currentRepoMeta ? currentRepoMeta.canonical_url : null;
  const defaultBranch = currentRepoMeta ? currentRepoMeta.default_branch : null;
  const filePathSet = _getFilePathSet(currentRepo);
  return _linkifyPaths(_linkifyCommitShas(html, canonicalUrl), canonicalUrl, defaultBranch, filePathSet);
}

/* =========================================================
   Spec 029: verified file-path set (lazy per-repo fetch + cache)
   ========================================================= */
const _filePathSetCache = {};

/** Lazily fetch and cache the repository's verified file-path Set from
 * GET /api/repos/{id}/file-paths. Fetched once per repo and reused on every
 * re-render (no refetch). A failed or empty response caches an empty Set, so
 * path-linking degrades to plain code (spec 029 AC-07) instead of erroring. */
async function _loadFilePathSet(repoId) {
  if (_filePathSetCache[repoId]) return _filePathSetCache[repoId];
  let paths = [];
  try {
    const data = await apiFetch(`/api/repos/${encodeURIComponent(repoId)}/file-paths`);
    paths = Array.isArray(data.paths) ? data.paths : [];
  } catch {
    paths = [];
  }
  const set = new Set(paths);
  _filePathSetCache[repoId] = set;
  return set;
}

/** The cached verified file-path Set for a repo, or an empty Set if it has not
 * been loaded yet (synchronous callers such as streaming Ask answers). */
function _getFilePathSet(repoId) {
  return _filePathSetCache[repoId] || new Set();
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
    if (e.status !== 404) {
      el.innerHTML = '<div class="empty-state" role="alert">Error loading case study.</div>';
      return;
    }
    // No narrative yet. If commits have already been analyzed, the case-study-only
    // regenerate endpoint can build a narrative without re-running commit analysis —
    // offer that instead of just telling the user to "run analysis first".
    const hasAnalyzedCommits = !!(currentRepoMeta && currentRepoMeta.analysis_count > 0);
    el.innerHTML = hasAnalyzedCommits
      ? `<div class="empty-state">
          <p>No case study generated yet.</p>
          <button class="analyze-btn" id="cs-generate-btn" style="margin-top:0.75rem;margin-left:0"
            onclick="_generateCaseStudy('${esc(repoId)}')" aria-label="Generate case study"
            title="Generate a case study narrative from the commits already analyzed">Generate case study</button>
        </div>`
      : '<div class="empty-state">No case study generated yet. Run analysis first.</div>';
    return;
  }
  const canonicalUrl = currentRepoMeta ? currentRepoMeta.canonical_url : data.repository_id;
  const sections = _splitNarrative(data.narrative || '');
  const words = (data.narrative || '').trim().split(/\s+/).length;
  const currentAudience = localStorage.getItem('cs-audience') || 'beginner';
  const chips = `<div class="meta-chips">
    <span class="chip" data-tip="statCommits" tabindex="0">${data.commit_count} commits</span>
    <span class="chip gray">${words} words</span>
    ${data.generated_at ? `<span class="chip gray">Generated ${fmtDate(data.generated_at)}</span>` : ''}
    <span class="cs-audience-wrap" title="Switch audience — cached versions load instantly; new levels generate in background (~1 min)">
      <span class="cs-audience-label">Audience:</span>
      <select class="cs-audience-select" onchange="_setCsAudience(this.value)" aria-label="Case study audience level">
        <option value="beginner"${currentAudience === 'beginner' ? ' selected' : ''}>${(data.available_audiences || []).includes('beginner') ? 'Beginner' : 'Beginner — generates (~1 min)'}</option>
        <option value="expert"${currentAudience === 'expert' ? ' selected' : ''}>${(data.available_audiences || []).includes('expert') ? 'Expert' : 'Expert — generates (~1 min)'}</option>
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
        : (useCards ? _renderSectionCards(s.content, s.title) : `<div class="markdown-body">${renderMarkdown(s.content)}</div>`);
      tabBtns += `<button class="cs-tab-btn${i === 0 ? ' active' : ''}" onclick="_csSwitchTab(${i})" role="tab" aria-selected="${i === 0}" aria-controls="cs-sec-${i}" id="cs-btn-${i}">${esc(s.title)}</button>`;
      tabPanels += `<div class="cs-section${i === 0 ? ' active' : ''}" id="cs-sec-${i}" role="tabpanel" aria-labelledby="cs-btn-${i}" tabindex="0">${body}</div>`;
    });
  } else {
    const html = renderMarkdown(data.narrative || '');
    tabPanels = `<div class="cs-section active"><div class="markdown-body">${html}</div></div>`;
  }

  // Fix 6: Linkify commit SHAs in the rendered panels
  // Spec 020: linkify file/folder paths in <code> spans — must run AFTER SHA
  // linking (see _linkifyPaths' doc comment for why the order matters).
  const defaultBranch = currentRepoMeta ? currentRepoMeta.default_branch : null;
  // Spec 029: lazily fetch (once) and cache the repo's verified file-path set so
  // _linkifyPaths only links tree-verified paths. Empty set => no links (AC-07).
  const filePathSet = await _loadFilePathSet(repoId);
  const linkedTabPanels = _linkifyPaths(
    _linkifyCommitShas(tabPanels, canonicalUrl),
    canonicalUrl,
    defaultBranch,
    filePathSet
  );

  el.innerHTML = `
    <div class="case-study-header">
      <div class="case-study-title">${esc(repoShortName(canonicalUrl))}</div>
      <div class="case-study-meta"><a href="${esc(canonicalUrl)}" target="_blank" rel="noopener">${esc(canonicalUrl)} ↗</a></div>
      ${chips}
    </div>
    ${sections.length > 0 ? `<div class="cs-tabs" role="tablist" aria-label="Case study sections">${tabBtns}</div>` : ''}
    ${linkedTabPanels}`;
}

/** Triggered by the empty Case Study tab's "Generate case study" button (shown
 * only when the repo has analyzed commits but no narrative yet). Calls the
 * case-study-only regenerate endpoint — no commit re-analysis — then reuses
 * the existing _pollRegenStatus polling loop, same as audience switching. */
async function _generateCaseStudy(repoId) {
  const el = document.getElementById('case-study-content');
  const audience = localStorage.getItem('cs-audience') || 'beginner';
  el.innerHTML = `<div class="empty-state">${spinner()}<p style="color:var(--yellow);margin-top:0.5rem">Generating case study… this may take a minute.</p></div>`;
  let regenRes;
  try {
    regenRes = await fetch(`/api/repos/${encodeURIComponent(repoId)}/case-study/regenerate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ audience }),
    });
  } catch {
    el.innerHTML = '<div class="empty-state" role="alert">Failed to start generation — check that the server is running.</div>';
    return;
  }
  if (!regenRes.ok) {
    el.innerHTML = `<div class="empty-state" role="alert">Generation failed (HTTP ${regenRes.status}). Try again.</div>`;
    return;
  }
  _pollRegenStatus(repoId, audience);
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
  // spec 021: surface a background regen failure instead of silently reloading as
  // if it had succeeded.
  let failedError = null;
  pollUntilDone({
    url: `/api/repos/${encodeURIComponent(repoId)}/case-study/regen-status`,
    interval: 2000,
    onTick: (s) => {
      if (s.running) return false;
      if (s.error) failedError = s.error;  // job stopped with a failure
      return true;
    },
    onDone: () => {
      if (failedError) {
        if (el) el.innerHTML = `<div class="empty-state" role="alert">Case study generation failed (${esc(failedError)}). Check the server logs and try again.</div>`;
        return;
      }
      loadCaseStudy(repoId);
    },
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
          ${analyzed ? `<button data-shas="${esc(JSON.stringify(shas))}" data-label="Hotspot: ${esc(fname)}" onclick="_filterHotspot(this)" style="font-size:11px;color:var(--text);text-decoration:underline;background:none;border:none;cursor:pointer;padding:0">${analyzed} analyzed →</button>` : ''}
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
        ? `<button data-shas="${esc(JSON.stringify(h.evidence_commit_shas||[]))}" data-label="Hotspot: ${esc(fname)}" onclick="event.stopPropagation();_filterHotspot(this)" style="font-size:12px;color:var(--text);text-decoration:underline;background:none;border:none;cursor:pointer;padding:0">${analyzedCount} →</button>`
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
  const bar = document.getElementById('commits-filter-bar');
  const descEl = document.getElementById('commits-filter-desc');
  if (bar) bar.style.display = 'flex';
  if (descEl) descEl.textContent = desc;
  _applyTimelineFilters();
}

function _clearCommitFilters() {
  const kw = document.getElementById('tl-search');
  const from = document.getElementById('tl-date-from');
  const to = document.getElementById('tl-date-to');
  if (kw) kw.value = '';
  if (from) from.value = '';
  if (to) to.value = '';
  _commitsCategorySelected = new Set();
  _renderCommitsCategoryChips();
  _evidenceShaFilter = null;
  _tlHourFilter = null;
  const bar = document.getElementById('commits-filter-bar');
  if (bar) bar.style.display = 'none';
  _applyTimelineFilters();
}

function _filterHotspot(btn) {
  try {
    const shas = JSON.parse(btn.dataset.shas || '[]');
    _filterByEvidenceShas(shas, btn.dataset.label || 'Hotspot');
  } catch {}
}

async function _filterByEvidenceShas(shas, label) {
  if (!currentRepo || !shas || !shas.length) return;
  switchTab('commits');
  if (!_tlAllCommits.length) await loadTimeline(currentRepo);
  _evidenceShaFilter = new Set(shas);
  _applyCommitFilter(label);
}

function _searchCommitsByFile(filePath) {
  if (!currentRepo) return;
  const keyword = filePath.split('/').pop();
  switchTab('commits');
  setTimeout(() => {
    const input = document.getElementById('tl-search');
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
  switchTab('commits');
  setTimeout(() => {
    const input = document.getElementById('tl-search');
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
    const matchingShas = _tlAllCommits
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
  switchTab('commits');
  setTimeout(() => {
    const input = document.getElementById('tl-search');
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

function _setAnalyzeStopState(visible, stopping = false) {
  const stopBtn = document.getElementById('sh-analyze-stop-btn');
  if (!stopBtn) return;
  stopBtn.style.display = visible ? '' : 'none';
  stopBtn.disabled = stopping;
  stopBtn.textContent = stopping ? 'Stopping…' : 'Stop';
  stopBtn.title = stopping ? 'Analysis stop requested' : 'Stop running analysis';
}

function _setAnalyzeProgressState(status) {
  const btn = document.getElementById('sh-analyze-btn');
  if (!btn) return;
  btn.disabled = true;
  btn.style.color = 'var(--yellow)';
  btn.style.display = '';
  if (status.cancel_requested) {
    btn.textContent = 'Stopping…';
  } else if (status.total > 0 && status.done >= status.total) {
    btn.textContent = 'Updating case study…';
  } else if (status.total > 0) {
    btn.textContent = `${status.done}/${status.total} analyzed`;
  } else {
    btn.textContent = 'Running…';
  }
  _setAnalyzeStopState(true, Boolean(status.cancel_requested));
}

async function _syncAnalyzeStatus(repoId) {
  try {
    const status = await apiFetch(`/api/repos/${encodeURIComponent(repoId)}/analyze/status`);
    if (currentRepo !== repoId) return;
    if (status.running) {
      _setAnalyzeProgressState(status);
      _pollAnalyzeStatus(repoId);
    } else {
      _setAnalyzeStopState(false);
    }
  } catch { /* non-critical */ }
}

async function _doAnalyze(limit) {
  if (!currentRepo) return;
  _hideAnalyzePicker();
  const btn = document.getElementById('sh-analyze-btn');
  _setAnalyzeStopState(false);

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
    _setAnalyzeStopState(true);
    _pollAnalyzeStatus(currentRepo);
  } catch (e) {
    alert(`Analysis failed: ${e.message}`);
    if (btn) { btn.textContent = '+ Analyze'; btn.disabled = false; btn.style.color = ''; }
    _setAnalyzeStopState(false);
  }
}

async function _cancelAnalyze() {
  if (!currentRepo) return;
  const repoId = currentRepo;
  _setAnalyzeStopState(true, true);
  const btn = document.getElementById('sh-analyze-btn');
  if (btn) { btn.textContent = 'Stopping…'; btn.disabled = true; btn.style.color = 'var(--yellow)'; }
  try {
    const res = await fetch(`/api/repos/${encodeURIComponent(repoId)}/analyze/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    if (res.ok || res.status === 409) {
      _pollAnalyzeStatus(repoId);
      return;
    }
    throw new Error(`HTTP ${res.status}`);
  } catch (e) {
    alert(`Could not stop analysis: ${e.message}`);
    _setAnalyzeStopState(true, false);
  }
}

function _pollAnalyzeStatus(repoId) {
  const btn = document.getElementById('sh-analyze-btn');
  if (_analyzePoll) clearInterval(_analyzePoll);
  // spec 021: a background job that stops with a non-null error must surface as a
  // FAILED state, not be silently treated as success. Captured here across ticks.
  let failedError = null;
  let finalStatus = null;
  _analyzePoll = pollUntilDone({
    url: `/api/repos/${encodeURIComponent(repoId)}/analyze/status`,
    interval: 2000,
    onTick: (s) => {
      if (!btn) return true;  // button removed from DOM — stop silently
      if (s.running) {
        _setAnalyzeProgressState(s);
        return false;
      }
      finalStatus = s;
      if (s.error) failedError = s.error;  // job stopped with a failure
      return true;
    },
    onDone: async () => {
      _analyzePoll = null;
      if (!btn) return;  // guard: button removed while polling
      if (failedError) {
        _setAnalyzeStopState(false);
        btn.textContent = 'Analysis failed';
        btn.style.color = 'var(--red)';
        btn.disabled = false;
        btn.title = `Analysis failed (${failedError}). Check the server logs and try again.`;
        setTimeout(() => {
          if (btn) { btn.textContent = '+ Analyze'; btn.style.color = ''; btn.title = ''; }
        }, 6000);
        return;
      }
      if (finalStatus?.cancelled) {
        _setAnalyzeStopState(false);
        btn.textContent = 'Stopped';
        btn.style.color = 'var(--yellow)';
        btn.disabled = false;
        try {
          await refreshCurrentRepoMeta(repoId);
          renderHeaderRepoMeta();
          const updated = await apiFetch(`/api/repos/${encodeURIComponent(repoId)}/analyze/estimate?limit=9999`);
          _analyzePrefetch = updated;
        } catch {}
        if (currentRepo === repoId && (finalStatus.done || 0) > 0) {
          loadTimeline(repoId);
          loadOverview(repoId);
          markUpdatedTabs(['overview', 'commits']);
        }
        setTimeout(() => {
          if (btn) { btn.textContent = '+ Analyze'; btn.style.color = ''; }
        }, 3000);
        return;
      }
      _setAnalyzeStopState(false);
      btn.textContent = '✓ Done!';
      btn.style.color = 'var(--green)';
      btn.disabled = false;
      // Refresh /api/repos-derived metadata so the header uses the same source as reload.
      try {
        await refreshCurrentRepoMeta(repoId);
        renderHeaderRepoMeta();
        const updated = await apiFetch(`/api/repos/${encodeURIComponent(repoId)}/analyze/estimate?limit=9999`);
        _analyzePrefetch = updated;
      } catch {}
      // Always reload timeline so _tlAllCommits is fresh regardless of which view is active
      if (currentRepo === repoId) loadTimeline(repoId);
      // Reload overview so its charts reflect the newly analyzed commits immediately
      if (currentRepo === repoId) loadOverview(repoId);
      // Reload case study — regenerated on backend after analysis
      if (currentRepo === repoId) loadCaseStudy(repoId);
      if (currentRepo === repoId) markUpdatedTabs(['overview', 'case-study', 'commits']);
      // Reset button after showing Done
      setTimeout(() => {
        if (btn) { btn.textContent = '+ Analyze'; btn.style.color = ''; }
      }, 3000);
    },
    onError: () => {
      _analyzePoll = null;
      if (btn) { btn.textContent = '+ Analyze'; btn.disabled = false; btn.style.color = ''; }
      _setAnalyzeStopState(false);
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
    <span style="color:var(--muted)">·</span> categories based on analyzed sample only
  </p>`;

  const top3 = humans.slice(0, 3);
  const rest = humans.slice(3);
  const RANK_LABELS = ['#1', '#2', '#3'];

  function renderCard(c, rank) {
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
    const tierClass = rank !== null ? ' is-top-tier' : '';
    const rankBadge = rank !== null ? `<span class="cc-rank" aria-label="Rank ${rank + 1}">${RANK_LABELS[rank]}</span>` : '';
    return `<div class="contributor-card${tierClass}">
      ${rankBadge}
      <div class="cc-top">
        <div class="cc-avatar" style="background:${bg}" aria-hidden="true">${esc(initials)}</div>
        <div style="flex:1">
          <div class="cc-name">${esc(c.author_name)}</div>
          <div class="cc-meta">${c.active_days} active day${c.active_days !== 1 ? 's' : ''}${isGitHub ? ` · <a href="${ghUrl}" target="_blank" rel="noopener" class="cc-gh-link">${ghLabel}</a>` : ''}</div>
        </div>
      </div>
      <div class="cc-stats">
        <span><strong>${c.commit_count}</strong> commits</span>
        <span style="font-size:10px;color:var(--muted)">${dateRange}</span>
      </div>
      ${cats.length ? `<div class="cc-cats">${cats.map(([cat, cnt]) => `<span class="badge ${badgeClass(cat)}" title="${cnt} commits">${esc(cat)}</span>`).join('')}</div>` : ''}
      ${topFiles.length ? `<div class="cc-files" style="flex-wrap:wrap;overflow:hidden;max-width:100%">Top files: ${topFiles.map(f => `<code style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:inline-block;vertical-align:bottom">${esc(f.split('/').pop())}</code>`).join('')}</div>` : ''}
    </div>`;
  }

  if (top3.length) {
    html += '<p class="contributors-top-label">Top contributors</p>';
    html += '<div class="contributor-grid">';
    top3.forEach((c, i) => { html += renderCard(c, i); });
    html += '</div>';
  }
  if (rest.length) {
    html += '<p class="contributors-rest-label">All contributors</p>';
    html += '<div class="contributor-grid">';
    rest.forEach(c => { html += renderCard(c, null); });
    html += '</div>';
  }
  el.innerHTML = html;
}

/* =========================================================
   Ask (GitItGPT) — spec 012 AC-6
   ========================================================= */
let _askHistory = [];
let _askRepoId = null;

function _resetAskTab(repoId) {
  _askHistory = [];
  _askRepoId = repoId;
  const transcript = document.getElementById('ask-transcript');
  if (transcript) transcript.innerHTML = '';
  const errEl = document.getElementById('ask-error');
  if (errEl) { errEl.style.display = 'none'; errEl.textContent = ''; }
}

function _appendAskMessage(role, text) {
  const transcript = document.getElementById('ask-transcript');
  if (!transcript) return null;
  const div = document.createElement('div');
  div.className = 'ask-msg ask-msg-' + role;
  div.innerHTML = role === 'assistant'
    ? `<div class="markdown-body">${_linkifyAskAnswerHtml(renderMarkdown(text))}</div>`
    : esc(text);
  transcript.appendChild(div);
  transcript.scrollTop = transcript.scrollHeight;
  return div;
}

/** Parse one buffered SSE chunk into complete frames + the leftover partial
 * frame (spec 013 AC-3/AC-4). Each frame is `{event, data}`, `data` parsed as
 * JSON (or null if it wasn't valid JSON). */
function _parseSseChunk(buffer) {
  const rawFrames = buffer.split('\n\n');
  const remainder = rawFrames.pop() ?? '';
  const frames = rawFrames.map(raw => {
    let event = 'message';
    let dataLine = '';
    raw.split('\n').forEach(line => {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) dataLine = line.slice(5).trim();
    });
    let data = null;
    try { data = dataLine ? JSON.parse(dataLine) : null; } catch { data = null; }
    return { event, data };
  });
  return { frames, remainder };
}

function _appendAskThinking() {
  const transcript = document.getElementById('ask-transcript');
  if (!transcript) return null;
  const div = document.createElement('div');
  div.className = 'ask-msg ask-msg-assistant ask-msg-thinking';
  div.setAttribute('aria-label', 'GitItGPT is thinking');
  div.innerHTML = '<span class="ask-thinking-dots"><span></span><span></span><span></span></span>';
  transcript.appendChild(div);
  transcript.scrollTop = transcript.scrollHeight;
  return div;
}

function _showAskError(message) {
  const errEl = document.getElementById('ask-error');
  if (!errEl) return;
  errEl.textContent = message;
  errEl.style.display = '';
}

const ASK_STREAM_SILENCE_TIMEOUT_MS = 30000;

async function _submitAskQuestion(message) {
  const errEl = document.getElementById('ask-error');
  if (errEl) { errEl.style.display = 'none'; errEl.textContent = ''; }
  _appendAskMessage('user', message);
  let thinkingEl = _appendAskThinking();

  const submitBtn = document.getElementById('ask-submit');
  if (submitBtn) submitBtn.disabled = true;

  const controller = new AbortController();
  let silenceTimer = null;
  const armSilenceTimer = () => {
    if (silenceTimer) clearTimeout(silenceTimer);
    silenceTimer = setTimeout(() => controller.abort(), ASK_STREAM_SILENCE_TIMEOUT_MS);
  };

  let bubbleEl = null;
  let accumulated = '';
  let terminal = null; // 'done' | 'error'

  try {
    armSilenceTimer();
    const res = await fetch(`/api/repos/${encodeURIComponent(currentRepo)}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, history: _askHistory }),
      signal: controller.signal,
    });
    if (!res.ok) {
      if (thinkingEl) thinkingEl.remove();
      _showAskError(
        res.status === 401
          ? 'Unauthorized — check the API key configuration.'
          : 'The assistant is temporarily unavailable. Please try again.'
      );
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      armSilenceTimer();
      buffer += decoder.decode(value, { stream: true });
      const { frames, remainder } = _parseSseChunk(buffer);
      buffer = remainder;

      for (const frame of frames) {
        if (frame.event === 'done') {
          terminal = 'done';
        } else if (frame.event === 'error') {
          terminal = 'error';
          if (thinkingEl) { thinkingEl.remove(); thinkingEl = null; }
          _showAskError(
            (frame.data && frame.data.message) ||
            'The assistant is temporarily unavailable. Please try again.'
          );
        } else if (frame.data && frame.data.text_delta) {
          if (thinkingEl) { thinkingEl.remove(); thinkingEl = null; }
          if (!bubbleEl) bubbleEl = _appendAskMessage('assistant', '');
          accumulated += frame.data.text_delta;
          bubbleEl.querySelector('.markdown-body').innerHTML = _linkifyAskAnswerHtml(renderMarkdown(accumulated));
          const transcript = document.getElementById('ask-transcript');
          if (transcript) transcript.scrollTop = transcript.scrollHeight;
        }
      }
    }

    if (terminal === 'done' && accumulated) {
      _askHistory.push({ role: 'user', content: message });
      _askHistory.push({ role: 'assistant', content: accumulated });
    } else if (terminal === null) {
      // The connection closed without a done/error frame — treat as a failure.
      if (thinkingEl) thinkingEl.remove();
      _showAskError('The assistant is temporarily unavailable. Please try again.');
    }
  } catch {
    if (thinkingEl) thinkingEl.remove();
    _showAskError(
      controller.signal.aborted
        ? 'The assistant took too long to respond. Please try again.'
        : 'Network error — could not reach the assistant.'
    );
  } finally {
    if (silenceTimer) clearTimeout(silenceTimer);
    if (submitBtn) submitBtn.disabled = false;
  }
}

const _askForm = document.getElementById('ask-form');
if (_askForm) {
  _askForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const input = document.getElementById('ask-input');
    const message = (input.value || '').trim();
    if (!message || !currentRepo) return;
    if (_askRepoId !== currentRepo) _resetAskTab(currentRepo);
    input.value = '';
    _submitAskQuestion(message);
  });
}

/* =========================================================
   Delete repository
   ========================================================= */

/**
 * Delete a repository by ID after user confirmation.
 * @param {string} repoId  - repository_id (e.g. "repo-abc123")
 * @param {string} repoUrl - canonical URL shown in the confirmation dialog
 * @param {HTMLElement|null} cardEl - card element to remove on success (null = detail page)
 */
async function deleteRepo(repoId, repoUrl, cardEl) {
  const label = repoUrl ? repoShortName(repoUrl) : repoId;
  if (!confirm(`Delete "${label}"?\n\nThis permanently removes all commits, analyses, and the case study. There is no undo.`)) {
    return;
  }
  try {
    const res = await fetch(`/api/repos/${encodeURIComponent(repoId)}`, { method: 'DELETE' });
    if (res.ok) {
      // Remove from local cache
      reposCache = reposCache.filter(r => r.repository_id !== repoId);
      renderSidebarRepos();
      if (cardEl) {
        // Home page: remove card from DOM without reloading
        cardEl.remove();
        const countEl = document.getElementById('repos-count');
        if (countEl) countEl.textContent = reposCache.length || '';
        if (reposCache.length === 0) renderRepoCards();
      } else {
        // Repo detail page: go back to home
        goHome();
      }
    } else if (res.status === 409) {
      alert('Cannot delete: an operation is in progress for this repository. Please wait and try again.');
    } else {
      const body = await res.json().catch(() => ({}));
      alert(`Delete failed: ${body.detail || `HTTP ${res.status}`}`);
    }
  } catch (err) {
    alert('Delete failed: could not reach the server.');
  }
}

/** Called from the Delete button in the repo detail header. */
function _confirmDeleteCurrentRepo() {
  if (!currentRepo) return;
  const url = currentRepoMeta?.canonical_url || '';
  deleteRepo(currentRepo, url, null);
}

/* =========================================================
   Boot
   ========================================================= */
async function boot() {
  await loadRepos();
  renderRepoCards();
}
boot();
