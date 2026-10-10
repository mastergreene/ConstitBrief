// Client-side "Ask Them Now" evaluation from /api/meta, so the checklist updates
// instantly as fields are typed and keeps working offline.
const filled = (v) => (typeof v === 'boolean' ? v : v != null && String(v).trim() !== '');

export function evaluate(meta, category, data, maybeInNotes = []) {
  const keys = meta.category_requirements[category] || meta.category_requirements.general;
  const out = [];
  for (const key of keys) {
    const r = meta.requirements[key];
    const applies = Object.entries(r.when || {}).every(([fid, allowed]) => allowed.includes(String(data[fid] ?? '')));
    if (!applies) continue;
    const checks = r.fields.map((f) => filled(data[f]));
    const met = r.mode === 'all' ? checks.every(Boolean) : checks.some(Boolean);
    out.push({ ...r, met, maybe_in_notes: !met && maybeInNotes.includes(key) });
  }
  const missing = out.filter((r) => !r.met);
  return {
    requirements: out,
    missing,
    completeness: out.length ? (out.length - missing.length) / out.length : 1,
    ready: !missing.some((r) => r.priority === 1),
  };
}
