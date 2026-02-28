/**
 * app.js — shared utilities for the speech evaluation platform (offline mode)
 *
 * Storage strategy:
 *   - Subject ID stored in sessionStorage
 *   - All collected results stored in localStorage under key "eval_results_<subjectId>"
 *   - On completion a JSON file is offered for download (duplicate-safe naming)
 */

// ── Session helpers ──────────────────────────────────────────────────────────

const Session = {
  get(key) { return sessionStorage.getItem(key); },
  set(key, val) { sessionStorage.setItem(key, typeof val === 'string' ? val : JSON.stringify(val)); },
  getJSON(key) { try { return JSON.parse(sessionStorage.getItem(key)); } catch { return null; } },
  clear() { sessionStorage.clear(); }
};

function requireAuth(redirectTo = 'login.html') {
  if (!Session.get('subject_id')) {
    location.href = redirectTo;
    return false;
  }
  return true;
}

// ── Seeded PRNG and Shuffle ────────────────────────────────────────────────────

// String hasher
function xmur3(str) {
  for (var i = 0, h = 1779033703 ^ str.length; i < str.length; i++) {
    h = Math.imul(h ^ str.charCodeAt(i), 3432918353);
    h = h << 13 | h >>> 19;
  }
  return function () {
    h = Math.imul(h ^ (h >>> 16), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    return (h ^= h >>> 16) >>> 0;
  }
}

// PRNG (returns float 0..1)
function mulberry32(a) {
  return function () {
    var t = a += 0x6D2B79F5;
    t = Math.imul(t ^ t >>> 15, t | 1);
    t ^= t + Math.imul(t ^ t >>> 7, t | 61);
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  }
}

// Get a deterministic RNG based on subject_id and phase
function getSeededRNG(subjectId, phase) {
  const seed = xmur3(subjectId + '_' + phase)();
  return mulberry32(seed);
}

// Fisher-Yates shuffle (accepts an RNG function, defaults to Math.random)
function shuffle(arr, rng = Math.random) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

// ── Offline data / save ───────────────────────────────────────────────────────

async function apiGetSets() {
  const res = await fetch('/api/sets');
  if (!res.ok) throw new Error('API fetch error');
  return res.json();
}

async function apiGetConfig() {
  const res = await fetch('/api/config');
  if (!res.ok) return { ab_test: { model_a: '', model_b: '' } };
  return res.json();
}

// ── State persistence (LocalStorage Resume) ─────────────────────────────────

function getLocalStateKey(phase) {
  const subjectId = Session.get('subject_id') || 'unknown';
  return `eval_state_${subjectId}_${phase}`;
}

function saveLocalState(phase, stateObj) {
  try {
    localStorage.setItem(getLocalStateKey(phase), JSON.stringify(stateObj));
  } catch (e) {
    console.warn('Could not save local state', e);
  }
}

function loadLocalState(phase) {
  try {
    const data = localStorage.getItem(getLocalStateKey(phase));
    return data ? JSON.parse(data) : null;
  } catch (e) {
    return null;
  }
}

function clearLocalState(phase) {
  try {
    localStorage.removeItem(getLocalStateKey(phase));
  } catch (e) { }
}

/**
 * Save results to backend API (/save).
 */
async function apiSave(phase, records) {
  const subjectId = Session.get('subject_id');
  const key = `eval_${subjectId}_${phase}`;

  // Persist in localStorage as well (backup)
  try { localStorage.setItem(key + '_' + Date.now(), JSON.stringify(records)); } catch { }

  // Send to backend server
  try {
    const res = await fetch('/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        subject_id: subjectId,
        phase: phase,
        records: records
      })
    });
    
    if (!res.ok) throw new Error('Failed to save on server');
    return await res.json();
  } catch (err) {
    console.error('API Save error:', err);
    alert('無法將結果儲存到伺服器！已為您打包下載備份記錄。');
    // Fallback: Download JSON file (duplicate-safe: timestamp guarantees uniqueness)
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    const filename = `${subjectId}_${phase}_${ts}.json`;
    const blob = new Blob([JSON.stringify(records, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
    return { ok: false, error: err.message };
  }
}

// ── Play button factory ──────────────────────────────────────────────────────

const ICON = { idle: '▶', playing: '⏸', done: '🔁' };

function makePlayButton(src) {
  const el = document.createElement('button');
  el.className = 'play-btn';
  el.innerHTML = `<span class="btn-icon">${ICON.idle}</span><span class="btn-label">Play</span>`;

  let audio = null;

  function setState(state) {
    el.className = 'play-btn' + (state === 'playing' ? ' playing' : state === 'done' ? ' done' : '');
    el.querySelector('.btn-icon').textContent = ICON[state] ?? ICON.idle;
    el.querySelector('.btn-label').textContent =
      state === 'playing' ? 'Pause' : state === 'done' ? 'Replay' : 'Play';
  }

  el.addEventListener('click', () => {
    if (!audio) {
      audio = new Audio(src);
      audio.addEventListener('ended', () => setState('done'));
    }
    if (audio.paused) {
      // Pause all other playing buttons first
      document.querySelectorAll('.play-btn.playing').forEach(b => { if (b !== el) b.click(); });
      audio.play();
      setState('playing');
    } else {
      if (audio.ended) {
        audio.currentTime = 0;
        audio.play();
        setState('playing');
      } else {
        audio.pause();
        setState('idle');
      }
    }
  });

  return {
    el,
    reset() {
      if (audio) { audio.pause(); audio = null; }
      setState('idle');
    }
  };
}

// ── Slider builder ───────────────────────────────────────────────────────────

function makeSlider(name, labelText, scaleLabels = null) {
  const wrap = document.createElement('div');
  wrap.className = 'metric-block';
  wrap.innerHTML = `
    <div class="metric-label">
      <span>${labelText}</span>
      <span class="metric-value" id="val-${name}">—</span>
    </div>
    <input class="likert-slider" type="range" min="1" max="5" step="1"
           name="${name}" id="slider-${name}" style="background:var(--border)">
    <div class="slider-endpoints"><span>1</span><span>2</span><span>3</span><span>4</span><span>5</span></div>
  `;
  const slider = wrap.querySelector('input');
  const valEl = wrap.querySelector('.metric-value');
  slider.dataset.touched = 'false';
  slider.value = 3;
  slider.addEventListener('input', () => {
    slider.dataset.touched = 'true';
    const v = parseInt(slider.value);
    valEl.textContent = scaleLabels ? `${v} ${scaleLabels[v - 1]}` : String(v);
    const pct = ((v - 1) / 4) * 100;
    slider.style.background = `linear-gradient(90deg, var(--accent) ${pct}%, var(--border) ${pct}%)`;
  });
  return { wrap, slider };
}

// ── Progress bar ─────────────────────────────────────────────────────────────

function updateProgress(current, total) {
  const label = document.getElementById('progress-label');
  const fill = document.getElementById('progress-fill');
  if (label) label.textContent = `Set ${current} / ${total}`;
  if (fill) fill.style.width = `${(current / total) * 100}%`;
}

// ── Language switcher ─────────────────────────────────────────────────────────
// Call on pages with .lang-zh / .lang-en blocks.

function initLangSwitcher() {
  const saved = localStorage.getItem('eval_lang') || 'zh';
  applyLang(saved);

  const widget = document.createElement('div');
  widget.className = 'lang-switcher';
  widget.innerHTML = `
    <button class="lang-btn" id="btn-zh">中文</button>
    <button class="lang-btn" id="btn-en">EN</button>
  `;
  document.body.appendChild(widget);

  document.getElementById('btn-zh').addEventListener('click', () => applyLang('zh'));
  document.getElementById('btn-en').addEventListener('click', () => applyLang('en'));

  function applyLang(lang) {
    document.body.classList.remove('lang-zh', 'lang-en');
    document.body.classList.add('lang-' + lang);
    localStorage.setItem('eval_lang', lang);
    const btnZh = document.getElementById('btn-zh');
    const btnEn = document.getElementById('btn-en');
    if (btnZh) btnZh.classList.toggle('active', lang === 'zh');
    if (btnEn) btnEn.classList.toggle('active', lang === 'en');
  }
}

// ── Nonverbal selector (two mutually exclusive radio options) ─────────────────
// Returns { wrap, getValue() } where getValue() returns 'laughing' | 'crying' | null

function makeNonverbalSelector(name) {
  const wrap = document.createElement('div');
  wrap.className = 'nv-selector';
  wrap.innerHTML = `
    <span class="nv-title">Presence of Nonverbal Cues</span>
    <label class="nv-option">
      <input type="radio" name="${name}" value="laughing">
      <span>Laughing</span>
    </label>
    <label class="nv-option">
      <input type="radio" name="${name}" value="crying">
      <span>Crying</span>
    </label>
  `;

  // Make radio buttons deselectable
  const radios = wrap.querySelectorAll('input[type=radio]');
  radios.forEach(radio => {
    radio.addEventListener('click', function (e) {
      if (this.wasChecked) {
        this.checked = false;
        this.wasChecked = false;
      } else {
        // Uncheck 'wasChecked' on all other radios in this group
        radios.forEach(r => r.wasChecked = false);
        this.wasChecked = true;
      }
    });

    // Also handle programmatic changes (e.g., when pre-filling state)
    radio.addEventListener('change', function () {
      if (this.checked) {
        radios.forEach(r => r.wasChecked = false);
        this.wasChecked = true;
      }
    });
  });

  return {
    wrap,
    getValue() {
      const checked = wrap.querySelector('input[type=radio]:checked');
      return checked ? checked.value : null;
    }
  };
}

// ── Custom audio player (play/pause + seekable progress bar + time) ───────────

function makeAudioPlayer(src) {
  const wrap = document.createElement('div');
  wrap.className = 'audio-player';
  wrap.innerHTML = `
    <button class="ap-btn" title="Play">▶</button>
    <div class="ap-track">
      <div class="ap-bar"><div class="ap-fill"></div></div>
      <span class="ap-time">—</span>
    </div>
  `;

  const btn = wrap.querySelector('.ap-btn');
  const fill = wrap.querySelector('.ap-fill');
  const time = wrap.querySelector('.ap-time');
  const bar = wrap.querySelector('.ap-bar');
  let audio = null;
  let rafId = null;

  function fmt(s) {
    const m = Math.floor(s / 60), ss = Math.floor(s % 60);
    return `${m}:${ss.toString().padStart(2, '0')}`;
  }
  function tick() {
    if (!audio) return;
    const pct = audio.duration ? (audio.currentTime / audio.duration) * 100 : 0;
    fill.style.width = pct + '%';
    time.textContent = `${fmt(audio.currentTime)} / ${fmt(audio.duration || 0)}`;
    if (!audio.paused) rafId = requestAnimationFrame(tick);
  }
  function stopOthers() {
    document.querySelectorAll('.audio-player').forEach(p => {
      if (p === wrap) return;
      const b = p.querySelector('.ap-btn');
      if (b) { b.textContent = '▶'; b.classList.remove('playing'); }
      // trigger pause via custom event
      p.dispatchEvent(new CustomEvent('ap-stop'));
    });
  }

  wrap.addEventListener('ap-stop', () => {
    if (audio && !audio.paused) { audio.pause(); btn.textContent = '▶'; btn.classList.remove('playing'); cancelAnimationFrame(rafId); }
  });

  btn.addEventListener('click', () => {
    if (!audio) {
      audio = new Audio(src);
      audio.addEventListener('loadedmetadata', () => {
        time.textContent = `0:00 / ${fmt(audio.duration)}`;
      });
      audio.addEventListener('ended', () => {
        btn.textContent = '↺'; btn.classList.remove('playing');
        cancelAnimationFrame(rafId); fill.style.width = '100%';
      });
    }
    if (audio.ended) {
      audio.currentTime = 0; stopOthers(); audio.play();
      btn.textContent = '⏸'; btn.classList.add('playing');
      rafId = requestAnimationFrame(tick);
    } else if (audio.paused) {
      stopOthers(); audio.play();
      btn.textContent = '⏸'; btn.classList.add('playing');
      rafId = requestAnimationFrame(tick);
    } else {
      audio.pause(); btn.textContent = '▶'; btn.classList.remove('playing');
      cancelAnimationFrame(rafId);
    }
  });

  bar.addEventListener('click', e => {
    if (!audio || !audio.duration) return;
    const r = bar.getBoundingClientRect();
    audio.currentTime = ((e.clientX - r.left) / r.width) * audio.duration;
    fill.style.width = (audio.currentTime / audio.duration * 100) + '%';
    time.textContent = `${fmt(audio.currentTime)} / ${fmt(audio.duration)}`;
  });

  return {
    wrap,
    reset() {
      if (audio) { audio.pause(); audio.currentTime = 0; audio = null; }
      cancelAnimationFrame(rafId);
      btn.textContent = '▶'; btn.classList.remove('playing');
      fill.style.width = '0%'; time.textContent = '—';
    }
  };
}
