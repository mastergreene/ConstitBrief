// Fetch wrapper: same-origin session cookie, CSRF header on writes, abortable requests.
export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === 'string' ? detail : detail?.message || 'Request failed');
    this.status = status;
    this.detail = detail;
  }
}
export class OfflineError extends Error {}

let onUnauthorised = () => {};
export function setUnauthorisedHandler(fn) { onUnauthorised = fn; }

export async function api(path, { method = 'GET', body, signal } = {}) {
  const headers = { Accept: 'application/json' };
  if (method !== 'GET') headers['X-ConstitBrief'] = '1';
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let res;
  try {
    res = await fetch(path, {
      method, headers, signal, credentials: 'same-origin',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw new OfflineError('Cannot reach the office server');
  }
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith('/api/auth/login')) onUnauthorised();
    throw new ApiError(res.status, data?.detail ?? res.statusText);
  }
  return data;
}
