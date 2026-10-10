// Mirrors backend/app/services/jotform.py so the Jotform link works with no signal.
const TFN = /\b(?:TFN|tax file(?: number)?)(?:\s+(?:is|was|=))?[:#\s-]*(\d{3}[ -]?\d{3}[ -]?\d{2,3})\b/gi;

export function redactTfn(text) { return (text || '').replace(TFN, '[TFN REMOVED - do not record TFNs]'); }
export function hasTfn(text) { TFN.lastIndex = 0; const r = TFN.test(text || ''); TFN.lastIndex = 0; return r; }

const filled = (v) => (typeof v === 'boolean' ? v : v != null && String(v).trim() !== '');

function fmt(field, value) {
  if (field && field.type === 'checkbox') return value === true || value === 'true' ? 'Yes' : 'Not confirmed';
  const s = String(value).trim();
  if (field && field.type === 'date' && /^\d{4}-\d{2}-\d{2}$/.test(s)) {
    const [y, m, d] = s.split('-');
    return `${d}/${m}/${y}`;
  }
  return s;
}

export function composeDetails(meta, category, data, notes, urgency = '') {
  const cat = meta.categories.find((c) => c.id === category) || meta.categories.find((c) => c.id === 'general');
  const skip = new Set([...Object.keys(meta.jotform.params), 'category']);
  const lines = [`Category: ${cat.label}`];
  if (urgency && urgency !== 'routine') lines.push(`Urgency: ${urgency.replace('_', ' ').toUpperCase()}`);
  for (const f of meta.fields) {
    if (!(f.categories.includes('*') || f.categories.includes(category)) || skip.has(f.id)) continue;
    const v = data[f.id];
    if (f.type === 'checkbox' || filled(v)) lines.push(`${f.label}: ${fmt(f, v)}`);
  }
  const n = redactTfn((notes || '').trim());
  if (n) lines.push('', 'Notes:', n);
  lines.push('', '(Prepared with the Moreton Casework Fast-Resolver)');
  return lines.join('\n');
}

const plus = (s) => encodeURIComponent(s)
  .replace(/[!'()*]/g, (ch) => `%${ch.charCodeAt(0).toString(16).toUpperCase()}`)
  .replace(/%20/g, '+');

function encode(params) {
  // Match Python's urlencode (spaces as '+') so both sides produce identical URLs.
  return Object.entries(params)
    .map(([k, v]) => `${plus(k)}=${plus(v)}`)
    .join('&');
}

export function buildJotformUrl(meta, category, data, notes, urgency = '') {
  const jf = meta.jotform;
  const params = {};
  for (const [fid, pname] of Object.entries(jf.params)) {
    if (filled(data[fid])) params[pname] = String(data[fid]).trim();
  }
  if (!params['address132[state]'] && filled(data.address_line1)) params['address132[state]'] = 'QLD';
  const typeA = jf.typea[category];
  if (typeA) params[jf.type_param] = typeA;

  const full = composeDetails(meta, category, data, notes, urgency);
  const make = (det) => `${jf.url}?${encode({ ...params, [jf.notes_param]: det })}`;
  let url = make(full);
  let truncated = false;
  if (url.length > jf.max_url_length) {
    truncated = true;
    const marker = '\n[...notes truncated - paste the full notes into the form]';
    let lo = 0; let hi = full.length;
    while (lo < hi) {
      const mid = Math.floor((lo + hi + 1) / 2);
      if (make(full.slice(0, mid) + marker).length <= jf.max_url_length) lo = mid; else hi = mid - 1;
    }
    url = make(full.slice(0, lo) + marker);
  }
  return { url, truncated, details: full };
}
