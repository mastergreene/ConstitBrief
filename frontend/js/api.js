// Thin fetch wrapper: access-code header, JSON, offline detection.
const TOKEN_KEY = 'cw.accessToken';

let tokenPrompt = null; // set by app.js: async () => string|null

export function setTokenPrompt(fn) { tokenPrompt = fn; }
export function getToken() { try { return localStorage.getItem(TOKEN_KEY) || ''; } catch { return ''; } }
function setToken(t) { try { localStorage.setItem(TOKEN_KEY, t); } catch { /* private mode */ } }

export class OfflineError extends Error {}

export async function api(path, { method = 'GET', body, retry = true } = {}) {
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const token = getToken();
  if (token) headers['X-Access-Token'] = token;
  let res;
  try {
    res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new OfflineError('Offline');
  }
  if (res.status === 401 && retry && tokenPrompt) {
    const t = await tokenPrompt();
    if (t) { setToken(t); return api(path, { method, body, retry: true }); }
  }
  if (res.status === 503 && res.headers.get('X-Offline') === '1') throw new OfflineError('Offline');
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* not json */ }
    throw new Error(typeof detail === 'string' ? detail : 'Request failed');
  }
  if (res.status === 204) return null;
  return res.json();
}
