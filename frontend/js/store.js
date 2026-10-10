// Local persistence: the in-progress call survives refreshes, flaky signal and app switches.
const CASE_KEY = 'cw.currentCase';
const CACHE_PREFIX = 'cw.cache.';

function read(key, fallback) {
  try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch { return fallback; }
}
function write(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* quota / private mode */ }
}

export function newCase() {
  const id = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`);
  return {
    client_id: id,
    category: null, // explicit chip choice; null = auto-detect
    notes: '',
    data: { state: 'QLD' },
    mode: 'resolve',
    status: 'open',
    selectedTemplates: [],
    triage: null,
    draft: '',
    updatedAt: Date.now(),
  };
}

export function loadCase() { return read(CASE_KEY, null) || newCase(); }

let timer = null;
export function saveCase(c) {
  c.updatedAt = Date.now();
  clearTimeout(timer);
  timer = setTimeout(() => write(CASE_KEY, c), 250);
}
export function saveCaseNow(c) { clearTimeout(timer); c.updatedAt = Date.now(); write(CASE_KEY, c); }

export const cache = {
  get: (k, fallback = null) => read(CACHE_PREFIX + k, fallback),
  set: (k, v) => write(CACHE_PREFIX + k, v),
};
