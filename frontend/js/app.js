import { api, ApiError, OfflineError, setUnauthorisedHandler } from './api.js';

/* =============================================================== helpers == */
const $ = (sel, root = document) => root.querySelector(sel);

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'text') el.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, v);
  }
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

let toastTimer;
function toast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 2600);
}

async function copy(text, label = 'Copied') {
  try { await navigator.clipboard.writeText(text); } catch {
    const ta = h('textarea', { class: 'visually-hidden' });
    ta.value = text; document.body.append(ta); ta.select(); document.execCommand('copy'); ta.remove();
  }
  toast(label);
}

const debounce = (fn, ms) => { let t; const d = (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; d.cancel = () => clearTimeout(t); return d; };
const filled = (v) => v != null && String(v).trim() !== '';
const errMsg = (e) => (e instanceof OfflineError ? 'Cannot reach the office server' : e.message || 'Something went wrong');

/** Re-render a section without losing keyboard focus inside it. */
function renderInto(container, nodes) {
  const active = document.activeElement;
  const key = container.contains(active) ? active.dataset.key : null;
  container.replaceChildren(...[nodes].flat(Infinity).filter(Boolean));
  if (key) container.querySelector(`[data-key="${CSS.escape(key)}"]`)?.focus();
}

/* ================================================================= state == */
// State defaults to QLD (visible and editable): the office only serves Moreton residents and the
// form requires a state.
const emptyState = () => ({
  values: { state: 'QLD' }, provenance: { state: 'default' }, rejected: {}, types: { selected: [], rejected: [] }, team: null,
  summary: { issue: '', outcome: '' }, not_applicable: [], dismissed_questions: [],
  approved_actions: [], dismissed_actions: [], custom_actions: [],
  deadlines_accepted: [], deadlines_dismissed: [], form_choice: {},
});

const S = {
  user: null, meta: null,
  inter: null, // { id, ref, version }
  notes: '',
  st: emptyState(),
  an: null,
  seq: 0, ctrl: null, modelCtrl: null,
  prepared: {}, // form option -> { result, recordHash }
  handoffRows: [],
  inputs: {},
  panel: 'notes',
  dirty: false, saving: false, lastAnnounce: '',
};

const SESSION_KEY = 'cb.current';
const typeById = (id) => S.meta.enquiry_types.find((t) => t.id === id);
const fieldById = (id) => S.meta.record_fields.find((f) => f.id === id);
const activeTypes = () => (S.st.types.selected.length ? S.st.types.selected : (S.an?.active_types || []));

function sessionWrite() {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify({ inter: S.inter, notes: S.notes, st: S.st, dirty: S.dirty }));
  } catch { /* storage unavailable */ }
}
function sessionRead() { try { return JSON.parse(sessionStorage.getItem(SESSION_KEY) || 'null'); } catch { return null; } }
function sessionClear() { try { sessionStorage.removeItem(SESSION_KEY); } catch { /* ignore */ } }

/* ============================================================ status UI == */
function setStatus(id, state, text) {
  const el = $(id);
  el.dataset.state = state;
  $('.txt', el).textContent = text;
}

function announce(text) {
  if (text === S.lastAnnounce) return;
  S.lastAnnounce = text;
  $('#sr-status').textContent = text;
}

/* ================================================================== auth == */
function showLogin() {
  $('#app-view').hidden = true;
  $('#login-view').hidden = false;
  $('#login-username').focus();
}

async function onLogin(e) {
  e.preventDefault();
  const err = $('#login-error');
  err.hidden = true;
  try {
    S.user = await api('/api/auth/login', { method: 'POST', body: { username: $('#login-username').value, password: $('#login-password').value } });
    $('#login-password').value = '';
    await startApp();
  } catch (ex) {
    err.textContent = errMsg(ex);
    err.hidden = false;
  }
}

async function logout() {
  await saveNow();
  try { await api('/api/auth/logout', { method: 'POST' }); } catch { /* ignore */ }
  sessionClear();
  resetWorkspace();
  S.user = null;
  showLogin();
}

/* ================================================================= boot == */
async function boot() {
  setUnauthorisedHandler(() => { if (S.user) { S.user = null; toast('Session expired - sign in again'); } showLogin(); });
  $('#login-form').addEventListener('submit', onLogin);
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
  try {
    S.user = await api('/api/auth/me');
    await startApp();
  } catch {
    showLogin();
  }
}

let wired = false;
async function startApp() {
  S.meta = await api('/api/meta');
  $('#login-view').hidden = true;
  $('#app-view').hidden = false;
  $('#user-name').textContent = S.user.display_name;
  $('#btn-library').hidden = S.user.role !== 'admin';
  $('#ephemeral-banner').hidden = !S.meta.features.ephemeral_storage;
  $('#retention-hours').textContent = S.meta.draft_retention_hours;
  if (!wired) { wire(); wired = true; }
  await restoreOrCreate();
}

async function restoreOrCreate() {
  const local = sessionRead();
  if (local?.inter?.id) {
    try {
      const srv = await api(`/api/interactions/${local.inter.id}`);
      const useLocal = local.dirty && local.inter.version >= srv.version;
      loadInteraction(srv, useLocal ? local : null);
      if (useLocal) scheduleSave();
      return;
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        await newInteraction({ carry: local });
        toast('The server copy had expired. Restored your notes from this tab.');
        return;
      }
      loadLocalOnly(local);
      return;
    }
  }
  await newInteraction();
}

function loadLocalOnly(local) {
  S.inter = local.inter; S.notes = local.notes || ''; S.st = { ...emptyState(), ...local.st }; S.dirty = true;
  renderAll();
  setStatus('#save-status', 'error', 'Not saved - server unreachable (kept in this tab)');
}

function loadInteraction(srv, local) {
  resetWorkspace();
  S.inter = { id: srv.id, ref: srv.ref, version: srv.version };
  S.notes = local ? local.notes : srv.notes;
  S.st = { ...emptyState(), ...(local ? local.st : srv.state) };
  S.handoffRows = srv.handoffs || [];
  S.dirty = Boolean(local);
  renderAll();
  setStatus('#save-status', 'ok', S.dirty ? 'Unsaved changes' : 'Saved');
  runAnalysis();
}

async function newInteraction({ carry } = {}) {
  const srv = await api('/api/interactions', { method: 'POST' });
  resetWorkspace();
  S.inter = { id: srv.id, ref: srv.ref, version: srv.version };
  if (carry) { S.notes = carry.notes || ''; S.st = { ...emptyState(), ...carry.st }; S.dirty = true; scheduleSave(); }
  renderAll();
  setStatus('#save-status', 'ok', carry ? 'Unsaved changes' : 'New - nothing to save yet');
  sessionWrite();
  if (S.notes) runAnalysis();
  $('#notes').focus();
}

/** Wipe every trace of the previous person from the UI and memory. */
function resetWorkspace() {
  S.ctrl?.abort(); S.modelCtrl?.abort();
  S.seq += 1;
  S.notes = ''; S.st = emptyState(); S.an = null; S.prepared = {}; S.handoffRows = [];
  S.inputs = {}; S.dirty = false; S.lastAnnounce = '';
  $('#notes').value = '';
  for (const id of ['#sec-alerts', '#sec-types', '#sec-team', '#sec-questions', '#sec-ready', '#sec-checklist',
    '#sec-details', '#sec-dates', '#sum-issue-prop', '#sum-outcome-prop', '#sec-actions', '#sec-guidance',
    '#search-results', '#handoff-list', '#ack-output']) $(id).replaceChildren();
  $('#sum-issue').value = ''; $('#sum-outcome').value = ''; $('#search-q').value = '';
  $('#tfn-warning').hidden = true;
  $('#badge-missing').hidden = true;
  setStatus('#analysis-status', 'idle', 'Assistant idle');
}

/* ================================================================= save == */
const scheduleSave = debounce(() => saveNow(), 1500);

function markDirty() {
  S.dirty = true;
  sessionWrite();
  setStatus('#save-status', 'busy', 'Unsaved changes');
  scheduleSave();
}

async function saveNow() {
  scheduleSave.cancel();
  if (!S.inter || !S.dirty || S.saving) return;
  S.saving = true;
  setStatus('#save-status', 'busy', 'Saving…');
  try {
    const r = await api(`/api/interactions/${S.inter.id}`, { method: 'PUT', body: { version: S.inter.version, notes: S.notes, state: S.st } });
    S.inter.version = r.version;
    S.dirty = false;
    sessionWrite();
    setStatus('#save-status', 'ok', `Saved ${new Date().toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' })}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) setStatus('#save-status', 'error', 'Changed in another window - reopen the draft');
    else setStatus('#save-status', 'error', 'Not saved - kept in this tab, retrying');
    if (!(e instanceof ApiError && e.status === 409)) setTimeout(() => { if (S.dirty) saveNow(); }, 8000);
  } finally {
    S.saving = false;
    if (S.dirty && $('#save-status').dataset.state !== 'error') scheduleSave();
  }
}

/* ============================================================= analysis == */
const scheduleAnalysis = debounce(() => runAnalysis(), 650);

async function runAnalysis() {
  const seq = ++S.seq;
  S.ctrl?.abort(); S.modelCtrl?.abort();
  const ctrl = new AbortController();
  S.ctrl = ctrl;
  setStatus('#analysis-status', 'busy', 'Updating…');
  const t0 = performance.now();
  try {
    const res = await api('/api/analyse', { method: 'POST', body: { notes: S.notes, state: S.st, model: false, seq }, signal: ctrl.signal });
    if (seq !== S.seq) return; // stale: newer typing has happened
    S.an = res;
    renderAssistant();
    const ms = Math.round(performance.now() - t0);
    setStatus('#analysis-status', 'ok', `Up to date · ${ms} ms`);
    if (S.meta.features.analysis_model && S.notes.trim()) runModel(seq);
  } catch (e) {
    if (e.name === 'AbortError' || seq !== S.seq) return;
    setStatus('#analysis-status', 'error', 'Assistant unavailable - continue manually');
  }
}

async function runModel(seq) {
  const ctrl = new AbortController();
  S.modelCtrl = ctrl;
  const t0 = performance.now();
  try {
    const res = await api('/api/analyse', { method: 'POST', body: { notes: S.notes, state: S.st, model: true, seq }, signal: ctrl.signal });
    if (seq !== S.seq) return;
    if (res.model_status === 'ok') {
      S.an = res;
      renderAssistant();
      setStatus('#analysis-status', 'ok', `Up to date · model ${Math.round(performance.now() - t0)} ms`);
    } else {
      setStatus('#analysis-status', 'ok', 'Up to date (rules only - model unavailable)');
    }
  } catch (e) {
    if (e.name !== 'AbortError' && seq === S.seq) setStatus('#analysis-status', 'ok', 'Up to date (rules only)');
  }
}

/** Every staff edit: persist, then refresh suggestions (staff values stay authoritative). */
function staffChanged({ fast = false } = {}) {
  markDirty();
  // Reflect the staff decision immediately, even if the assistant is unavailable.
  renderTypes(); renderTeam(); renderDetails(); renderDates(); renderActions(); renderHandoffs();
  if (fast) { scheduleAnalysis.cancel(); runAnalysis(); } else scheduleAnalysis();
}

/* =============================================================== render == */
function renderAll() {
  $('#inter-ref').textContent = S.inter?.ref || '–';
  $('#notes').value = S.notes;
  $('#tfn-warning').hidden = !/\b(?:TFN|tax file(?: number)?)\b[^\n]{0,12}\d{3}/i.test(S.notes);
  $('#sum-issue').value = S.st.summary.issue || '';
  $('#sum-outcome').value = S.st.summary.outcome || '';
  renderAssistant();
}

function renderAssistant() {
  renderAlerts(); renderTypes(); renderTeam(); renderQuestions(); renderReadiness();
  renderDetails(); renderDates(); renderSummaryProps(); renderActions(); renderHandoffs();
  scheduleGuidance();
  const a = S.an;
  if (a) {
    const first = a.handoffs[0];
    const missing = first ? first.mandatory_missing.length : 0;
    const badge = $('#badge-missing');
    badge.hidden = !missing;
    badge.textContent = String(missing);
    badge.setAttribute('aria-label', `${missing} mandatory items missing`);
    announce(first ? `${missing ? `${missing} mandatory item${missing > 1 ? 's' : ''} missing` : 'All mandatory form fields captured'} for ${first.form_option}. ${a.questions.length} suggested questions.` : '');
  }
}

const CONF = (c) => (c >= 0.75 ? 'High' : c >= 0.5 ? 'Medium' : 'Low');

function renderAlerts() {
  const a = S.an;
  const out = [];
  if (a?.safety_flags?.length) {
    for (const f of a.safety_flags) {
      out.push(h('div', { class: 'alert alert-danger', role: 'note' }, `⚠ ${f.label} (staff judgement): `,
        f.referrals.map((r, i) => [i ? ' · ' : '', /^[\d ]+$/.test(r.contact) ? h('a', { href: `tel:${r.contact.replace(/\s/g, '')}` }, `${r.name} ${r.contact}`) : `${r.name} ${r.contact}`])));
    }
  }
  if (a?.contradictions?.length) {
    out.push(h('div', { class: 'alert alert-warn' }, h('strong', {}, 'Check these. The notes conflict:'),
      h('ul', {}, a.contradictions.map((c) => h('li', {}, c.message, ' ',
        h('button', { class: 'btn btn-xs btn-ghost', type: 'button', 'data-key': `cf-${c.field}`, onclick: () => focusField(c.field) }, 'Go to field'))))));
  }
  if (a?.uncertain) out.push(h('div', { class: 'alert alert-info' }, 'The type of work is uncertain. Ask a clarifying question, or choose the work type yourself.'));
  renderInto($('#sec-alerts'), out);
}

function setTypes(mutator) {
  if (!S.st.types.selected.length) S.st.types.selected = [...(S.an?.active_types || [])];
  mutator(S.st.types.selected);
  S.st.types.selected = [...new Set(S.st.types.selected)];
  staffChanged({ fast: true });
}

function renderTypes() {
  const a = S.an;
  const staff = S.st.types.selected.length > 0;
  const active = activeTypes();
  const sugg = (a?.enquiry_types || []);
  const ids = [...new Set([...active, ...sugg.map((s) => s.id)])].filter((id) => !S.st.types.rejected.includes(id));
  if (!ids.length) {
    renderInto($('#sec-types'), h('p', { class: 'muted' }, 'Start typing notes, or add a work type below.'));
  } else {
    renderInto($('#sec-types'), ids.map((id) => {
      const t = typeById(id);
      const s = sugg.find((x) => x.id === id);
      const on = active.includes(id);
      const primary = active[0] === id;
      return h('div', { class: `type-row${staff ? '' : ' suggested'}` },
        h('input', {
          type: 'checkbox', id: `ty-${id}`, 'data-key': `ty-${id}`, checked: on,
          'aria-label': `Include ${t.label}`,
          onchange: (e) => setTypes((sel) => { const i = sel.indexOf(id); if (e.target.checked && i < 0) sel.push(id); if (!e.target.checked && i >= 0) sel.splice(i, 1); }),
        }),
        h('div', { class: 'grow' },
          h('label', { for: `ty-${id}` }, h('strong', {}, t.label)),
          ' ', primary && on ? h('span', { class: 'tag info' }, 'Primary') : null,
          s ? h('span', { class: 'tag' }, `${CONF(s.confidence)} confidence`) : h('span', { class: 'tag' }, 'Added by you'),
          s ? h('div', { class: 'why' }, s.rationale) : null),
        on && !primary ? h('button', { class: 'btn btn-xs btn-ghost', type: 'button', 'data-key': `pr-${id}`, onclick: () => setTypes((sel) => { sel.splice(sel.indexOf(id), 1); sel.unshift(id); }) }, 'Make primary') : null,
        h('button', {
          class: 'btn btn-xs btn-ghost', type: 'button', 'data-key': `rj-${id}`, 'aria-label': `Not ${t.label}`,
          onclick: () => { S.st.types.rejected.push(id); setTypes((sel) => { const i = sel.indexOf(id); if (i >= 0) sel.splice(i, 1); }); },
        }, 'Not this'));
    }));
  }
}

function renderTeam() {
  const sug = S.an?.team;
  const sel = h('select', { id: 'team-select', 'data-key': 'team' },
    h('option', { value: '' }, sug?.team ? `Suggested: ${S.meta.teams[sug.team]}` : 'Staff to decide'),
    Object.entries(S.meta.teams).map(([k, v]) => h('option', { value: k }, v)));
  sel.value = S.st.team || '';
  sel.addEventListener('change', () => { S.st.team = sel.value || null; staffChanged(); });
  const basis = { confirmed: 'confirmed office guidance', proposed: 'proposed default: office to confirm', staff: 'staff to decide' };
  renderInto($('#sec-team'), [
    h('label', { class: 'label', for: 'team-select' }, 'Responsible team'), sel,
    h('p', { class: 'muted small' }, S.st.team ? 'Set by you.' : sug ? `${sug.rationale}` : ''),
    sug && !S.st.team ? h('span', { class: `tag ${sug.basis === 'confirmed' ? 'ok' : 'warn'}` }, basis[sug.basis]) : null,
  ]);
}

function renderQuestions() {
  const qs = S.an?.questions || [];
  if (!qs.length) { renderInto($('#sec-questions'), h('li', { class: 'muted' }, S.an ? 'Nothing outstanding.' : 'Questions appear as you type.')); return; }
  renderInto($('#sec-questions'), qs.map((q) => h('li', {},
    h('span', { class: 'q' }, q.text), h('br'),
    h('span', { class: 'why' }, q.reason),
    h('span', { class: 'acts' },
      q.key.startsWith('form:') || q.key.includes(':') ? h('button', { class: 'btn btn-xs btn-ghost', type: 'button', 'data-key': `go-${q.key}`, onclick: () => { const it = S.an.checklist.find((c) => c.key === q.key); focusField(it?.fields?.[0]); } }, 'Answer') : null,
      h('button', { class: 'btn btn-xs btn-ghost', type: 'button', 'data-key': `dq-${q.key}`, onclick: () => { S.st.dismissed_questions.push(q.key); staffChanged({ fast: true }); } }, 'Dismiss'),
      S.an.checklist.some((c) => c.key === q.key) && !q.key.startsWith('form:') ? h('button', { class: 'btn btn-xs btn-ghost', type: 'button', 'data-key': `na-${q.key}`, onclick: () => { S.st.not_applicable.push(q.key); staffChanged({ fast: true }); } }, 'N/A') : null))));
}

const STATUS = {
  collected: ['ok', '✓ Collected'], missing: ['danger', '✗ Missing'], unclear: ['warn', '? Unclear'], not_applicable: ['', '– N/A'],
};

function renderReadiness() {
  const a = S.an;
  if (!a) { renderInto($('#sec-ready'), h('p', { class: 'muted' }, 'Readiness appears once there is something to check.')); return; }
  renderInto($('#sec-ready'), a.handoffs.length ? a.handoffs.map((hf, i) => h('div', { class: `alert ${hf.ready ? 'alert-ok' : 'alert-warn'}` },
    h('strong', {}, `${i === 0 ? 'Primary' : 'Also'}: ${hf.form_option}`), ' ',
    hf.ready ? '✓ Mandatory form fields captured' : `✗ Mandatory: ${hf.mandatory_missing.join(', ')}`,
    hf.optional_missing.length ? h('div', { class: 'small' }, `Could improve: ${hf.optional_missing.slice(0, 6).join(', ')}${hf.optional_missing.length > 6 ? '…' : ''}`) : null,
    hf.form_option_basis === 'staff' ? h('div', { class: 'small' }, 'Form option is a suggestion: confirm it on the handoff tab.') : null))
    : h('p', { class: 'muted' }, 'No Jotform handoff applies to the selected work.'));
  const groups = [['form_required', 'Required by the Jotform'], ['form_optional', 'Asked on the Jotform (optional)'], ['suggestion', 'Suggested prompts (not office-verified requirements)']];
  renderInto($('#sec-checklist'), groups.map(([basis, title]) => {
    const items = a.checklist.filter((c) => c.basis === basis);
    if (!items.length) return null;
    return [h('h3', {}, title), h('ul', { class: 'ck' }, items.map((c) => {
      const [cls, txt] = STATUS[c.status];
      return h('li', {}, h('span', { class: `tag ${cls}` }, txt), ' ',
        h('button', { class: 'linkish', type: 'button', 'data-key': `ck-${c.key}`, onclick: () => focusField(c.fields[0]) }, c.label),
        c.status === 'not_applicable' ? h('button', { class: 'btn btn-xs btn-ghost', type: 'button', onclick: () => { S.st.not_applicable = S.st.not_applicable.filter((k) => k !== c.key); staffChanged({ fast: true }); } }, 'Undo') : null);
    }))];
  }));
}

/* ------------------------------------------------------------- details -- */
const CONTACT = ['first_name', 'last_name', 'phone', 'email', 'address_line1', 'suburb', 'state', 'postcode'];

function detailGroups() {
  const groups = [{ title: 'Contact', fields: [...CONTACT] }];
  const seen = new Set(CONTACT);
  for (const id of activeTypes()) {
    const t = typeById(id);
    const opt = S.st.form_choice[id] || t.form_option;
    const branch = opt ? S.meta.form.branches[opt] || [] : [];
    const fields = [];
    for (const e of branch) {
      const recs = typeof e.record === 'string' ? [e.record] : e.record ? Object.values(e.record) : [];
      fields.push(...recs);
    }
    for (const s of t.suggestions) fields.push(...s.fields.filter((f) => !f.startsWith('@')));
    const uniq = fields.filter((f) => fieldById(f) && !seen.has(f));
    uniq.forEach((f) => seen.add(f));
    if (uniq.length) groups.push({ title: t.label, fields: uniq });
  }
  // Values already captured, or found in the notes, for fields not otherwise shown.
  const extra = [...Object.keys(S.st.values), ...(S.an?.proposals || []).map((p) => p.field)]
    .filter((f) => fieldById(f) && !seen.has(f));
  if (extra.length) groups.push({ title: 'Other details', fields: [...new Set(extra)] });
  return groups;
}

function fieldControl(fid) {
  if (S.inputs[fid]) return S.inputs[fid];
  const f = fieldById(fid);
  const id = `fd-${fid}`;
  let input;
  if (f.type === 'select') input = h('select', { id }, h('option', { value: '' }, '–'), f.options.map((o) => h('option', { value: o }, o)));
  else if (f.type === 'textarea') input = h('textarea', { id, rows: '2' });
  else input = h('input', { id, type: f.type === 'date' ? 'date' : f.type, autocomplete: 'off' });
  const onChange = () => {
    const v = input.value;
    if (filled(v)) { S.st.values[fid] = v; S.st.provenance[fid] = 'staff'; } else { delete S.st.values[fid]; delete S.st.provenance[fid]; }
    staffChanged();
  };
  input.addEventListener(f.type === 'select' || f.type === 'date' ? 'change' : 'input', onChange);
  const prop = h('div', {});
  const wrap = h('div', { class: 'field', 'data-field': fid },
    h('label', { class: 'label', for: id }, f.label, f.sensitivity === 'identifier' ? h('span', { class: 'tag', title: 'Identifier: collect only if needed' }, ' identifier') : null),
    input, f.help ? h('div', { class: 'muted small' }, f.help) : null, prop);
  S.inputs[fid] = { wrap, input, prop };
  return S.inputs[fid];
}

function renderDetails() {
  const box = $('#sec-details');
  const groups = detailGroups();
  const nodes = [];
  for (const g of groups) {
    const grid = h('div', { class: 'grid' });
    for (const fid of g.fields) {
      const c = fieldControl(fid);
      if (document.activeElement !== c.input) c.input.value = S.st.values[fid] ?? '';
      renderProposal(fid, c.prop);
      grid.append(c.wrap);
    }
    nodes.push(h('div', { class: 'field-group' }, h('h3', {}, g.title), grid));
  }
  // Move persistent field elements into the new layout without recreating them.
  const active = document.activeElement;
  box.replaceChildren(...nodes);
  if (active && box.contains(active)) active.focus();
}

function renderProposal(fid, box) {
  const props = (S.an?.proposals || []).filter((p) => p.field === fid);
  const conflicts = (S.an?.contradictions || []).filter((c) => c.field === fid);
  const nodes = props.map((p) => h('div', { class: 'prop' },
    'From notes: ', h('q', {}, p.evidence.text), ' → ', h('strong', {}, p.value),
    h('button', { class: 'btn btn-xs btn-primary', type: 'button', 'data-key': `ac-${fid}`, onclick: () => { S.st.values[fid] = p.value; S.st.provenance[fid] = 'accepted'; S.inputs[fid].input.value = p.value; staffChanged({ fast: true }); } }, 'Use'),
    h('button', { class: 'btn btn-xs btn-ghost', type: 'button', 'data-key': `rjv-${fid}`, onclick: () => { (S.st.rejected[fid] ||= []).push(p.value); staffChanged({ fast: true }); } }, 'Not right')));
  for (const c of conflicts) nodes.push(h('div', { class: 'alert alert-warn small' }, `⚠ ${c.message}`));
  if (S.st.provenance[fid] === 'accepted' && !props.length) nodes.push(h('div', { class: 'muted small' }, 'Accepted from notes'));
  renderInto(box, nodes);
}

function focusField(fid) {
  if (!fid) return;
  if (fid === '@outcome') { setPanel('assistant'); $('#sum-outcome').focus(); return; }
  if (fid === '@details') { setPanel('assistant'); $('#sum-issue').focus(); return; }
  if (fid === '@deadline') { setPanel('assistant'); $('#sec-dates').scrollIntoView({ block: 'center' }); return; }
  const c = S.inputs[fid] || (fieldById(fid) && (renderDetails(), S.inputs[fid]));
  if (!c) return;
  setPanel('assistant');
  c.wrap.scrollIntoView({ behavior: 'smooth', block: 'center' });
  c.wrap.classList.add('focus-flash');
  setTimeout(() => c.wrap.classList.remove('focus-flash'), 1500);
  c.input.focus({ preventScroll: true });
}

/* -------------------------------------------------------------- dates --- */
function renderDates() {
  const ds = S.an?.dates || [];
  const acc = S.st.deadlines_accepted;
  const nodes = [];
  for (const d of acc) {
    nodes.push(h('div', { class: 'alert alert-ok' }, `✓ Deadline (confirmed by you): ${d.text}`, ' ',
      h('button', { class: 'btn btn-xs btn-ghost', type: 'button', onclick: () => { S.st.deadlines_accepted = acc.filter((x) => x !== d); staffChanged({ fast: true }); } }, 'Remove')));
  }
  const eventFieldShown = activeTypes().includes('event_invitation');
  for (const d of ds) {
    const key = `dt-${d.text}`;
    nodes.push(h('div', { class: `alert ${d.kind === 'deadline' ? 'alert-warn' : 'alert-info'}` },
      h('strong', {}, d.kind === 'deadline' ? '⏰ Stated deadline: ' : d.kind === 'event' ? 'Event date mentioned: ' : 'Date mentioned: '),
      `“${d.text}”`, d.needs_confirmation ? ' (needs an exact date)' : '',
      h('div', { class: 'small muted' }, `…${d.evidence.text}…`),
      h('div', { class: 'row wrap' },
        h('button', {
          class: 'btn btn-xs btn-primary', type: 'button', 'data-key': `${key}-dl`,
          onclick: () => {
            const exact = window.prompt('Confirm the deadline exactly as agreed (e.g. 3pm Friday 16 October):', d.iso ? `${d.text} (${d.iso})` : d.text);
            if (!exact) return;
            S.st.deadlines_accepted.push({ text: exact.trim(), source: d.text });
            staffChanged({ fast: true });
          },
        }, 'Confirm as deadline'),
        d.iso && eventFieldShown ? h('button', { class: 'btn btn-xs btn-ghost', type: 'button', onclick: () => { S.st.values.event_date = d.iso; S.st.provenance.event_date = 'accepted'; S.st.deadlines_dismissed.push(d.text); staffChanged({ fast: true }); } }, `Use ${d.iso} as event date`) : null,
        h('button', { class: 'btn btn-xs btn-ghost', type: 'button', 'data-key': `${key}-x`, onclick: () => { S.st.deadlines_dismissed.push(d.text); staffChanged({ fast: true }); } }, 'Dismiss'))));
  }
  renderInto($('#sec-dates'), nodes.length ? nodes : h('p', { class: 'muted' }, 'No dates or deadlines mentioned yet.'));
}

/* ------------------------------------------------------------ summary --- */
function renderSummaryProps() {
  const p = S.an?.summary_proposal || {};
  const mk = (which, text, target) => (text && !filled(S.st.summary[which])
    ? h('div', { class: 'prop' }, 'Suggestion: ', h('q', {}, text), h('button', { class: 'btn btn-xs btn-primary', type: 'button', onclick: () => { S.st.summary[which] = text; target.value = text; staffChanged(); } }, 'Use'))
    : null);
  renderInto($('#sum-issue-prop'), mk('issue', p.issue, $('#sum-issue')));
  renderInto($('#sum-outcome-prop'), mk('outcome', p.outcome?.text, $('#sum-outcome')));
}

/* ------------------------------------------------------------ actions --- */
function renderActions() {
  const acts = S.an?.actions || [];
  const nodes = acts.map((a) => {
    const on = S.st.approved_actions.includes(a.text);
    const id = `act-${a.key}`;
    return h('div', { class: 'check' },
      h('input', { type: 'checkbox', id, 'data-key': id, checked: on, onchange: (e) => { if (e.target.checked) S.st.approved_actions.push(a.text); else S.st.approved_actions = S.st.approved_actions.filter((x) => x !== a.text); staffChanged(); } }),
      h('label', { for: id }, a.text, h('span', { class: 'muted small' }, on ? ' (approved)' : ' (suggested)')),
      h('button', { class: 'btn btn-xs btn-ghost', type: 'button', onclick: () => { S.st.dismissed_actions.push(a.key); S.st.approved_actions = S.st.approved_actions.filter((x) => x !== a.text); staffChanged({ fast: true }); } }, 'Dismiss'));
  });
  for (const c of S.st.custom_actions) {
    nodes.push(h('div', { class: 'check' }, h('span', { class: 'tag ok' }, '✓ Yours'), c,
      h('button', { class: 'btn btn-xs btn-ghost', type: 'button', onclick: () => { S.st.custom_actions = S.st.custom_actions.filter((x) => x !== c); S.st.approved_actions = S.st.approved_actions.filter((x) => x !== c); staffChanged(); } }, 'Remove')));
  }
  renderInto($('#sec-actions'), nodes.length ? nodes : h('p', { class: 'muted' }, 'No follow-up actions suggested.'));
}

/* ----------------------------------------------------------- guidance --- */
let guidanceKey = '';
const scheduleGuidance = debounce(async () => {
  const types = activeTypes();
  const key = types.join(',');
  if (!S.an || key === guidanceKey) return;
  guidanceKey = key;
  try {
    const items = await api('/api/guidance', { method: 'POST', body: { types, notes: S.notes } });
    renderInto($('#sec-guidance'), items.length ? items.map((t) => h('details', { class: 'result' },
      h('summary', {}, h('strong', {}, t.title), ' ', h('span', { class: 'tag ok' }, `Approved ${t.last_reviewed || ''}`)),
      h('p', { class: 'small' }, t.summary), h('pre', { class: 'box' }, t.body),
      t.source_urls.length ? h('p', { class: 'small' }, 'Source: ', t.source_urls.map((u, i) => [i ? ', ' : '', h('a', { href: u, target: '_blank', rel: 'noopener noreferrer' }, u)])) : null,
      h('button', { class: 'btn btn-xs btn-ghost', type: 'button', onclick: () => copy(t.body) }, 'Copy')))
      : h('p', { class: 'muted' }, 'No approved guidance for this work yet.'));
  } catch { /* guidance is optional */ }
}, 1200);

/* ============================================================ handoffs == */
function recordHash() {
  return JSON.stringify([S.st.values, S.st.summary, S.st.approved_actions, S.st.deadlines_accepted]);
}

function plannedHandoffs() {
  const byOption = new Map();
  for (const id of activeTypes()) {
    const t = typeById(id);
    const opt = S.st.form_choice[id] || t.form_option;
    if (!opt) continue;
    if (!byOption.has(opt)) byOption.set(opt, { option: opt, types: [], basis: t.form_option_basis, primaryType: id });
    byOption.get(opt).types.push(id);
  }
  return [...byOption.values()];
}

const STATUS_TEXT = {
  prepared: 'Reviewed, not yet submitted',
  opened: 'Jotform opened. Submission NOT confirmed yet',
  reported_submitted: 'Submitted (reported by staff)',
  confirmed: 'Confirmed in Jotform',
  cancelled: 'Cancelled',
};

function renderHandoffs() {
  const list = $('#handoff-list');
  if (!S.meta) return;
  const plans = plannedHandoffs();
  if (!plans.length) { renderInto(list, h('p', { class: 'muted' }, 'Select the work involved on the Assistant tab to plan a handoff.')); return; }
  renderInto(list, plans.map((p, i) => handoffCard(p, i)));
}

function handoffCard(plan, idx) {
  const row = [...S.handoffRows].reverse().find((r) => r.form_option === plan.option && r.status !== 'cancelled');
  const prep = S.prepared[plan.option];
  const stale = prep && prep.recordHash !== recordHash();
  const t = typeById(plan.primaryType);
  const optSel = h('select', { 'aria-label': 'Jotform option', 'data-key': `opt-${plan.primaryType}` }, S.meta.form.options.map((o) => h('option', { value: o }, o)));
  optSel.value = plan.option;
  optSel.addEventListener('change', () => { for (const tid of plan.types) S.st.form_choice[tid] = optSel.value; delete S.prepared[plan.option]; staffChanged(); });
  const ready = S.an?.handoffs.find((x) => x.form_option === plan.option);
  const card = h('div', { class: 'handoff' },
    h('header', {},
      h('strong', {}, `Handoff ${idx + 1}: ${plan.types.map((x) => typeById(x).label).join(' + ')}`),
      row ? h('span', { class: `tag ${row.status === 'confirmed' || row.status === 'reported_submitted' ? 'ok' : row.status === 'opened' ? 'warn' : 'info'}` }, STATUS_TEXT[row.status]) : h('span', { class: 'tag' }, 'Not reviewed')),
    h('label', { class: 'label' }, 'Jotform “How can we help you?” option'), optSel,
    h('p', { class: 'small muted' }, plan.basis === 'staff' ? `No dedicated form option for ${t.label.toLowerCase()}: confirm this choice.` : 'Option verified against the live form.'),
    ready && !prep ? h('p', { class: `alert ${ready.ready ? 'alert-ok' : 'alert-warn'} small` }, ready.ready ? '✓ Mandatory fields captured' : `Mandatory fields missing: ${ready.mandatory_missing.join(', ')}`) : null,
    h('div', { class: 'row wrap' },
      h('button', { class: 'btn btn-primary', type: 'button', 'data-key': `rv-${plan.option}`, onclick: (e) => prepare(plan, e.currentTarget) }, prep ? (stale ? 'Review again (record changed)' : 'Refresh review') : 'Review mapping'),
      row && ['opened', 'reported_submitted'].includes(row.status) && S.meta.features.jotform_verification ? h('button', { class: 'btn btn-ghost', type: 'button', onclick: (e) => verify(row, e.currentTarget) }, 'Check Jotform for this reference') : null),
    row?.status === 'opened' ? h('div', { class: 'alert alert-warn' }, 'Did you submit the form?', h('div', { class: 'row wrap' },
      h('button', { class: 'btn btn-sm btn-primary', type: 'button', onclick: (e) => reportSubmitted(row, true, e.currentTarget) }, 'Yes, submitted'),
      h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: (e) => reportSubmitted(row, false, e.currentTarget) }, 'No, not submitted'))) : null,
    row?.submission_id ? h('p', { class: 'small' }, `Jotform submission: ${row.submission_id}`) : null,
    row && ['reported_submitted', 'confirmed'].includes(row.status) ? h('p', { class: 'small muted' }, 'A submission acknowledgement does not prove every notification email was delivered.') : null,
    prep ? preparedView(plan, prep, row, stale) : null);
  return card;
}

function preparedView(plan, prep, row, stale) {
  const r = prep.result;
  const rowsBySection = [];
  let lastSection;
  for (const x of r.rows) {
    if (x.section !== lastSection) { rowsBySection.push(h('tr', { class: 'sect' }, h('td', { colspan: '3' }, x.section ? `Section shown for “${r.form_option}”` : 'Always shown'))); lastSection = x.section; }
    const missing = x.required && !x.value && x.kind !== 'upload';
    rowsBySection.push(h('tr', { class: missing ? 'req-missing' : '' },
      h('th', { scope: 'row' }, x.label, x.required ? h('span', { 'aria-label': 'required' }, ' *') : null),
      h('td', { class: 'val' }, x.kind === 'upload' ? h('em', {}, x.note) : x.value || (missing ? '✗ Missing (required)' : '-')),
      h('td', {}, x.value ? h('button', { class: 'btn btn-xs btn-ghost', type: 'button', onclick: () => copy(x.value, `Copied ${x.label}`) }, 'Copy') : null)));
  }
  const allText = r.rows.filter((x) => x.value).map((x) => `${x.label}: ${x.value}`).join('\n');
  const canOpen = r.valid && !stale && (!row || ['prepared', 'opened'].includes(row.status));
  return h('div', {},
    stale ? h('p', { class: 'alert alert-warn' }, 'The record changed after this review. Review again before submitting.') : null,
    r.errors.length ? h('div', { class: 'alert alert-danger', role: 'alert' }, h('strong', {}, 'Can\'t submit yet. The form requires:'), h('ul', {}, r.errors.map((e) => h('li', {}, e)))) : null,
    r.warnings.map((w) => h('p', { class: 'alert alert-info small' }, w)),
    h('table', { class: 'map-table' }, h('caption', { class: 'visually-hidden' }, 'Jotform field mapping'),
      h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, 'Jotform field'), h('th', { scope: 'col' }, 'Value'), h('th', { scope: 'col' }, h('span', { class: 'visually-hidden' }, 'Copy')))),
      h('tbody', {}, rowsBySection)),
    r.unplaced_details.length ? h('div', { class: 'alert alert-warn' }, h('strong', {}, 'No form field for these details. Pass them on separately:'),
      h('pre', { class: 'box' }, r.unplaced_details.map(([k, v]) => `${k}: ${v}`).join('\n')),
      h('button', { class: 'btn btn-xs btn-ghost', type: 'button', onclick: () => copy(r.unplaced_details.map(([k, v]) => `${k}: ${v}`).join('\n')) }, 'Copy details')) : null,
    h('p', { class: 'small muted' }, `${r.url_policy} Reference ${prep.result.handoff.ref}. Mapping ${r.mapping_version}. Team: ${S.st.team ? S.meta.teams[S.st.team] : r.team.team ? `${S.meta.teams[r.team.team]} (suggested)` : 'staff to decide'}.`),
    h('div', { class: 'row wrap' },
      h('button', { class: 'btn btn-ghost', type: 'button', onclick: () => copy(allText, 'All fields copied') }, 'Copy all fields'),
      h('button', {
        class: 'btn btn-primary', type: 'button', disabled: !canOpen,
        'aria-describedby': canOpen ? null : `why-${plan.option}`,
        onclick: (e) => openJotform(plan, prep, e.currentTarget),
      }, 'Open Jotform to submit'),
      canOpen ? null : h('span', { id: `why-${plan.option}`, class: 'small muted' }, stale ? 'Review again first.' : !r.valid ? 'Complete the required fields first.' : 'Already submitted.')),
    row && row.status === 'prepared' ? h('button', { class: 'btn btn-xs btn-ghost', type: 'button', onclick: () => cancelHandoff(row) }, 'Cancel this handoff') : null);
}

async function prepare(plan, btn, additional = false) {
  btn.disabled = true;
  await saveNow();
  const body = {
    interaction_id: S.inter.id, type_id: plan.primaryType, form_option: plan.option,
    values: S.st.values, summary: S.st.summary, additional,
    approved_actions: [...S.st.approved_actions],
    confirmed_deadlines: S.st.deadlines_accepted.map((d) => d.text),
  };
  try {
    const result = await api('/api/handoffs/prepare', { method: 'POST', body });
    S.prepared[plan.option] = { result, recordHash: recordHash() };
    upsertRow(result.handoff);
  } catch (e) {
    if (e instanceof ApiError && e.status === 409 && e.detail?.existing) {
      const ex = e.detail.existing.at(-1);
      if (window.confirm(`A handoff for “${plan.option}” was already ${ex.status === 'confirmed' ? 'confirmed' : 'reported as submitted'} (${ex.ref}).\n\nSubmitting again will create a duplicate in Jotform. Prepare an ADDITIONAL submission anyway?`)) {
        return prepare(plan, btn, true);
      }
    } else toast(errMsg(e));
  } finally {
    btn.disabled = false;
    renderHandoffs();
  }
}

function upsertRow(row) {
  const i = S.handoffRows.findIndex((r) => r.id === row.id);
  if (i >= 0) S.handoffRows[i] = row; else S.handoffRows.push(row);
}

async function openJotform(plan, prep, btn) {
  btn.disabled = true; // double-click guard
  const w = window.open('about:blank', '_blank');
  try {
    const row = await api(`/api/handoffs/${prep.result.handoff.id}/opened`, { method: 'POST', body: { payload_hash: prep.result.handoff.payload_hash } });
    upsertRow(row);
    if (w) { w.opener = null; w.location.href = prep.result.form_url; } else window.open(prep.result.form_url, '_blank', 'noopener');
    toast('Paste the fields into the form, submit it, then record the outcome here.');
  } catch (e) {
    w?.close();
    toast(errMsg(e));
  } finally {
    renderHandoffs();
  }
}

async function reportSubmitted(row, submitted, btn) {
  btn.disabled = true;
  let sid = '';
  if (submitted) sid = window.prompt('Jotform submission ID, if you have it (optional):', '') || '';
  try { upsertRow(await api(`/api/handoffs/${row.id}/report`, { method: 'POST', body: { submitted, submission_id: sid } })); } catch (e) { toast(errMsg(e)); }
  renderHandoffs();
}

async function verify(row, btn) {
  btn.disabled = true;
  try {
    const r = await api(`/api/handoffs/${row.id}/verify`, { method: 'POST' });
    upsertRow(r.handoff);
    toast(r.found ? 'Found in Jotform' : 'Not found in Jotform yet. Status unchanged.');
  } catch (e) { toast(errMsg(e)); }
  renderHandoffs();
}

async function cancelHandoff(row) {
  try { upsertRow(await api(`/api/handoffs/${row.id}/cancel`, { method: 'POST' })); delete S.prepared[row.form_option]; } catch (e) { toast(errMsg(e)); }
  renderHandoffs();
}

/* ======================================================== other actions == */
async function writeAck() {
  const btn = $('#btn-ack');
  btn.disabled = true;
  try {
    const d = await api('/api/generate', { method: 'POST', body: { type_id: activeTypes()[0] || 'admin', values: S.st.values, notes: S.notes, template_ids: [] } });
    const email = h('textarea', { rows: '10', 'aria-label': 'Email draft' }); email.value = d.email;
    const sms = h('textarea', { rows: '3', 'aria-label': 'SMS draft' }); sms.value = d.sms;
    $('#ack-output').replaceChildren(
      h('p', { class: 'small muted' }, 'Review before sending. It doesn\'t promise outcomes, funding or attendance.'),
      h('label', { class: 'label' }, 'Subject'), h('input', { value: d.subject }),
      h('label', { class: 'label' }, 'Email'), email, h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: () => copy(email.value) }, 'Copy email'),
      h('label', { class: 'label' }, 'SMS'), sms, h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: () => copy(sms.value) }, 'Copy SMS'));
  } catch (e) { toast(errMsg(e)); }
  btn.disabled = false;
}

async function runSearch(e) {
  e.preventDefault();
  const q = $('#search-q').value.trim();
  if (!q) return;
  const box = $('#search-results');
  box.replaceChildren(h('p', { class: 'muted' }, 'Searching…'));
  try {
    const r = await api('/api/search', { method: 'POST', body: { q, type_id: activeTypes()[0] || null } });
    const nodes = [];
    if (r.error) nodes.push(h('p', { class: 'alert alert-warn' }, r.error));
    for (const x of r.results) nodes.push(h('div', { class: 'result' }, h('a', { href: x.url, target: '_blank', rel: 'noopener noreferrer' }, x.title), h('div', { class: 'domain' }, x.domain), h('p', { class: 'small' }, x.snippet)));
    if (!r.results.length) nodes.push(h('p', { class: 'small muted' }, r.provider ? 'No official results.' : 'Live search isn\'t configured. Open a site-restricted search:'), ...r.links.map((l) => h('div', {}, h('a', { href: l.url, target: '_blank', rel: 'noopener noreferrer' }, `Search ${l.domain}`))));
    if (r.directory.length) nodes.push(h('h3', {}, 'Key contacts'), h('ul', {}, r.directory.map((d) => h('li', {}, `${d.name}: ${d.phone || d.url}`))));
    box.replaceChildren(...nodes);
  } catch (ex) { box.replaceChildren(h('p', { class: 'alert alert-warn' }, errMsg(ex))); }
}

async function finishInteraction() {
  const uncertain = S.handoffRows.filter((r) => r.status === 'opened');
  const msg = uncertain.length
    ? `Submission for ${uncertain.map((r) => r.form_option).join(', ')} is NOT confirmed. Finish and clear anyway?`
    : 'Clear this interaction\'s notes and record now?';
  if (!window.confirm(msg)) return;
  try {
    await api(`/api/interactions/${S.inter.id}`, { method: 'DELETE' });
  } catch (e) { if (!(e instanceof ApiError && e.status === 404)) { toast(errMsg(e)); return; } }
  sessionClear();
  await newInteraction();
  toast('Cleared. Ready for the next person.');
}

async function startNew() {
  if ((S.notes.trim() || Object.keys(S.st.values).some((k) => k !== 'state')) && !window.confirm('Start a new interaction? This one stays in “Open draft” until it expires.')) return;
  await saveNow();
  sessionClear();
  await newInteraction();
}

async function openDrafts() {
  const dlg = $('#drafts-dialog');
  const list = $('#drafts-list');
  list.replaceChildren(h('li', { class: 'muted' }, 'Loading…'));
  dlg.showModal();
  try {
    const rows = await api('/api/interactions');
    list.replaceChildren(...rows.map((r) => h('li', {},
      h('strong', {}, r.ref), ' ', h('span', { class: 'muted small' }, `updated ${new Date(r.updated_at).toLocaleString('en-AU')}`),
      h('div', { class: 'small' }, r.preview || '(no notes)'),
      r.id === S.inter.id ? h('span', { class: 'tag info' }, 'Current') : h('button', {
        class: 'btn btn-sm btn-primary', type: 'button',
        onclick: async () => { await saveNow(); dlg.close(); loadInteraction(await api(`/api/interactions/${r.id}`), null); },
      }, 'Open'))));
    if (!rows.length) list.append(h('li', { class: 'muted' }, 'No open drafts.'));
  } catch (e) { list.replaceChildren(h('li', {}, errMsg(e))); }
}

/* -------------------------------------------------------------- library -- */
let editing = null;
async function openLibrary() {
  const dlg = $('#library-dialog');
  dlg.showModal();
  await renderLibrary();
}
async function renderLibrary() {
  const list = $('#library-list');
  try {
    const items = await api('/api/templates');
    list.replaceChildren(...items.map((t) => h('li', {},
      h('strong', {}, t.title), ' ', t.needs_review ? h('span', { class: 'tag warn' }, 'Needs review: not shown to staff') : h('span', { class: 'tag ok' }, `Approved ${t.last_reviewed || ''}${t.reviewed_by ? ` by ${t.reviewed_by}` : ''}`),
      h('div', { class: 'small muted' }, `${typeById(t.category)?.label || t.category} · ${t.summary}`),
      h('button', { class: 'btn btn-xs btn-ghost', type: 'button', onclick: () => openEditor(t) }, 'Edit / review'))));
  } catch (e) { list.replaceChildren(h('li', {}, errMsg(e))); }
}
function openEditor(t) {
  editing = t;
  $('#t-category').replaceChildren(...S.meta.enquiry_types.map((x) => h('option', { value: x.id }, x.label)));
  $('#tmpl-dialog-title').textContent = t ? 'Edit entry' : 'New entry';
  $('#t-title').value = t?.title || ''; $('#t-category').value = t?.category || 'admin';
  $('#t-tags').value = (t?.tags || []).join(', '); $('#t-summary').value = t?.summary || '';
  $('#t-sms').value = t?.sms || ''; $('#t-body').value = t?.body || '';
  $('#t-sources').value = (t?.source_urls || []).join('\n'); $('#t-approve').checked = false;
  $('#btn-tmpl-delete').hidden = !t;
  $('#tmpl-dialog').showModal();
}
async function saveTemplate(e) {
  if (e.submitter?.value !== 'save') return;
  e.preventDefault();
  const body = {
    title: $('#t-title').value.trim(), category: $('#t-category').value,
    tags: $('#t-tags').value.split(',').map((s) => s.trim()).filter(Boolean),
    summary: $('#t-summary').value.trim(), sms: $('#t-sms').value.trim(), body: $('#t-body').value.trim(),
    source_urls: $('#t-sources').value.split('\n').map((s) => s.trim()).filter((s) => /^https?:\/\//.test(s)),
  };
  try {
    if (editing) await api(`/api/templates/${editing.id}`, { method: 'PATCH', body: { ...body, approve: $('#t-approve').checked } });
    else {
      const created = await api('/api/templates', { method: 'POST', body });
      if ($('#t-approve').checked) await api(`/api/templates/${created.id}`, { method: 'PATCH', body: { approve: true } });
    }
    $('#tmpl-dialog').close();
    guidanceKey = '';
    renderLibrary();
  } catch (ex) { toast(errMsg(ex)); }
}

/* ================================================================ panels == */
const desktop = window.matchMedia('(min-width: 1000px)');
function setPanel(p) {
  if (desktop.matches && p === 'notes') p = S.panel === 'notes' ? 'assistant' : S.panel;
  S.panel = p;
  for (const name of ['notes', 'assistant', 'handoff']) {
    const tab = $(`#tab-${name}`);
    const on = name === p;
    tab.setAttribute('aria-selected', String(on));
    tab.tabIndex = on ? 0 : -1;
    $(`#panel-${name}`).hidden = !on && !(desktop.matches && name === 'notes');
  }
  if (p === 'handoff') renderHandoffs();
}

function wire() {
  const notes = $('#notes');
  notes.addEventListener('input', () => {
    S.notes = notes.value;
    $('#tfn-warning').hidden = !/\b(?:TFN|tax file(?: number)?)\b[^\n]{0,12}\d{3}/i.test(S.notes);
    markDirty();
    setStatus('#analysis-status', 'busy', 'Waiting for a pause…');
    scheduleAnalysis();
  });
  $('#sum-issue').addEventListener('input', (e) => { S.st.summary.issue = e.target.value; staffChanged(); });
  $('#sum-outcome').addEventListener('input', (e) => { S.st.summary.outcome = e.target.value; staffChanged(); });
  $('#add-type').addEventListener('change', (e) => {
    const id = e.target.value; e.target.value = '';
    if (!id) return;
    S.st.types.rejected = S.st.types.rejected.filter((x) => x !== id);
    setTypes((sel) => sel.push(id));
  });
  $('#add-type').replaceChildren(h('option', { value: '' }, 'Choose…'), ...S.meta.enquiry_types.map((t) => h('option', { value: t.id }, t.label)));
  $('#custom-action-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const v = $('#custom-action').value.trim();
    if (!v) return;
    S.st.custom_actions.push(v); S.st.approved_actions.push(v); $('#custom-action').value = '';
    renderActions(); staffChanged();
  });
  $('#search-form').addEventListener('submit', runSearch);
  $('#btn-ack').addEventListener('click', writeAck);
  $('#btn-finish').addEventListener('click', finishInteraction);
  $('#btn-new').addEventListener('click', startNew);
  $('#btn-user').addEventListener('click', logout);
  $('#btn-drafts').addEventListener('click', openDrafts);
  $('#btn-library').addEventListener('click', openLibrary);
  $('#btn-lib-new').addEventListener('click', () => openEditor(null));
  $('#tmpl-form').addEventListener('submit', saveTemplate);
  $('#btn-tmpl-delete').addEventListener('click', async () => {
    if (!editing || !window.confirm(`Delete “${editing.title}”?`)) return;
    try { await api(`/api/templates/${editing.id}`, { method: 'DELETE' }); $('#tmpl-dialog').close(); renderLibrary(); } catch (ex) { toast(errMsg(ex)); }
  });
  document.querySelectorAll('dialog [data-close]').forEach((b) => b.addEventListener('click', () => b.closest('dialog').close()));

  const tabs = [...document.querySelectorAll('.panel-tabs [role="tab"]')];
  tabs.forEach((t) => t.addEventListener('click', () => setPanel(t.dataset.panel)));
  $('.panel-tabs').addEventListener('keydown', (e) => {
    if (!['ArrowLeft', 'ArrowRight'].includes(e.key)) return;
    const vis = tabs.filter((t) => t.offsetParent !== null);
    const i = vis.indexOf(document.activeElement);
    const next = vis[(i + (e.key === 'ArrowRight' ? 1 : vis.length - 1)) % vis.length];
    next.focus(); setPanel(next.dataset.panel);
  });
  desktop.addEventListener('change', () => setPanel(desktop.matches && S.panel === 'notes' ? 'assistant' : S.panel));
  new ResizeObserver(() => document.documentElement.style.setProperty('--topbar-h', `${$('.topbar').offsetHeight}px`)).observe($('.topbar'));
  setPanel(desktop.matches ? 'assistant' : 'notes');

  window.addEventListener('beforeunload', (e) => { if (S.dirty) { sessionWrite(); saveNow(); e.preventDefault(); } });
}

boot();
