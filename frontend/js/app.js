import { api, OfflineError, setTokenPrompt } from './api.js';
import { buildJotformUrl, hasTfn } from './jotform.js';
import { evaluate } from './requirements.js';
import { createDictation } from './speech.js';
import { cache, loadCase, newCase, saveCase, saveCaseNow } from './store.js';

// ------------------------------------------------------------------ helpers --
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
  for (const c of children.flat()) {
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
  toastTimer = setTimeout(() => { t.hidden = true; }, 2200);
}

async function copy(text, label = 'Copied') {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = h('textarea', { class: 'visually-hidden' });
    ta.value = text;
    document.body.append(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
  }
  toast(label);
}

const telHref = (p) => `tel:${String(p).replace(/[^\d+]/g, '')}`;
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

// -------------------------------------------------------------------- state --
const S = {
  meta: null,
  c: loadCase(),
  templates: cache.get('templates', []),
  view: 'resolve',
  online: navigator.onLine,
  searchDomains: new Set(),
};

const cat = () => S.c.category || S.c.triage?.category || 'general';
const catLabel = (id) => S.meta.categories.find((x) => x.id === id)?.label || id;
const persist = () => saveCase(S.c);

// ---------------------------------------------------------------------- boot --
async function loadMeta() {
  try {
    S.meta = await api('/api/meta');
    cache.set('meta', S.meta);
  } catch (e) {
    S.meta = cache.get('meta');
    if (!S.meta) throw e;
  }
}

async function loadTemplates() {
  try {
    S.templates = await api('/api/templates');
    cache.set('templates', S.templates);
  } catch { /* keep cached copy */ }
}

function setOnline(on) {
  S.online = on;
  const el = $('#net-status');
  el.textContent = on ? 'Online' : 'Offline';
  el.className = `pill ${on ? 'pill-ok' : 'pill-warn'}`;
}

function renderEngineStatus() {
  const f = S.meta.features;
  const bits = [f.jev ? 'Jev triage' : 'Rule triage', f.search_provider ? 'live search' : 'search links'];
  $('#engine-status').textContent = bits.join(' · ');
  $('#search-provider').textContent = f.search_provider ? `via ${f.search_provider}` : 'no search key: links only';
}

async function boot() {
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
  window.addEventListener('online', () => { setOnline(true); syncCase(); });
  window.addEventListener('offline', () => setOnline(false));
  setOnline(navigator.onLine);
  setTokenPrompt(promptToken);

  try {
    await loadMeta();
  } catch {
    $('#engine-status').textContent = 'Cannot reach the office server';
    toast('Cannot reach the office server');
    return;
  }
  renderEngineStatus();
  bindIntake();
  bindResolve();
  bindEscalate();
  bindLibrary();
  bindTabs();
  restoreCase();
  loadTemplates().then(() => { renderAdvice(); renderLibrary(); });
}

// ----------------------------------------------------------- access token --
function promptToken() {
  const dlg = $('#token-dialog');
  if (dlg.open) return Promise.resolve(null);
  $('#token-input').value = '';
  dlg.showModal();
  return new Promise((resolve) => {
    dlg.addEventListener('close', () => resolve($('#token-input').value.trim() || null), { once: true });
  });
}

// ---------------------------------------------------------------- intake --
function renderChips() {
  const box = $('#category-chips');
  box.replaceChildren();
  const detected = S.c.triage?.category;
  const mk = (id, label) => h('button', {
    class: 'chip', type: 'button', role: 'radio',
    'aria-checked': String((S.c.category || null) === id),
    onclick: () => {
      S.c.category = id;
      persist();
      renderChips();
      renderForm();
      refreshEscalate();
      updateSearchDomains();
    },
  }, label);
  box.append(mk(null, detected && !S.c.category ? `Auto: ${S.meta.categories.find((x) => x.id === detected)?.short}` : 'Auto-detect'));
  for (const c of S.meta.categories) box.append(mk(c.id, c.short));
}

function bindIntake() {
  const notes = $('#notes');
  notes.addEventListener('input', () => {
    S.c.notes = notes.value;
    $('#tfn-warning').hidden = !hasTfn(notes.value);
    persist();
    refreshJotform();
    autosave();
  });
  $('#btn-triage').addEventListener('click', runTriage);
  $('#btn-new-case').addEventListener('click', startNewCase);

  const mic = $('#btn-mic');
  const dict = createDictation({
    onText: (t) => {
      notes.value = notes.value ? `${notes.value.replace(/\s+$/, '')} ${t}` : t;
      notes.dispatchEvent(new Event('input'));
    },
    onState: (on, err) => {
      mic.setAttribute('aria-pressed', String(on));
      mic.setAttribute('aria-label', on ? 'Stop dictation' : 'Start dictation');
      if (err) toast(err);
    },
  });
  if (!dict) mic.hidden = true;
  else mic.addEventListener('click', () => dict.toggle());
}

async function runTriage() {
  const btn = $('#btn-triage');
  btn.disabled = true;
  btn.textContent = 'Triaging…';
  try {
    const t = await api('/api/triage', { method: 'POST', body: { notes: S.c.notes, category: S.c.category, data: S.c.data } });
    S.c.triage = t;
    S.c.mode = t.mode;
    persist();
    renderTriage();
    renderChips();
    renderForm();
    renderAdvice();
    refreshEscalate();
    updateSearchDomains();
    if (!$('#search-q').value && t.search_query) $('#search-q').value = t.search_query;
    autosave();
  } catch (e) {
    if (e instanceof OfflineError) {
      toast('Offline: checklist still works, matching needs signal');
      setView('escalate');
    } else {
      toast(e.message);
    }
  } finally {
    btn.disabled = false;
    btn.textContent = 'Triage';
  }
}

function renderTriage() {
  const t = S.c.triage;
  const sum = $('#triage-summary');
  const safety = $('#safety');
  if (!t) { sum.hidden = true; safety.hidden = true; $('#escalate-dot').hidden = true; return; }

  safety.replaceChildren();
  if (t.safety_flags.length) {
    for (const f of t.safety_flags) {
      safety.append(
        h('h3', { text: `⚠ ${f.label}` }),
        h('ul', {}, f.referrals.map((r) => h('li', {}, /^[\d ]+$/.test(r.contact)
          ? h('a', { href: telHref(r.contact) }, `${r.name}: ${r.contact}`)
          : h('a', { href: `https://${r.contact}`, target: '_blank', rel: 'noopener noreferrer' }, `${r.name}: ${r.contact}`)))),
      );
    }
    safety.hidden = false;
  } else safety.hidden = true;

  const urgClass = { routine: 'pill-ok', time_sensitive: 'pill-warn', urgent: 'pill-danger' }[t.urgency];
  const esc = t.mode === 'escalate';
  sum.replaceChildren(
    h('span', { class: 'pill' }, catLabel(t.category)),
    h('span', { class: `pill ${urgClass}` }, t.urgency.replace('_', ' ')),
    h('span', { class: `pill ${esc ? 'pill-danger' : 'pill-ok'}` }, esc ? 'Likely needs representation' : 'Try to resolve now'),
    h('span', { class: 'muted small' }, t.engine === 'jev+rules' ? 'Jev' : 'rules'),
    h('button', {
      class: `btn btn-sm ${esc ? 'btn-accent' : 'btn-ghost'}`, type: 'button',
      onclick: () => setView(esc ? 'escalate' : 'resolve'),
    }, esc ? 'Escalate →' : 'Resolve →'),
  );
  sum.hidden = false;
  $('#escalate-dot').hidden = !esc || S.view === 'escalate';
}

// --------------------------------------------------------------- resolve --
function renderAdvice() {
  const list = $('#advice-list');
  list.replaceChildren();
  let items = S.c.triage?.suggested_templates || [];
  // Use the freshest copy of each template from the library.
  items = items.map((s) => S.templates.find((t) => t.id === s.id) || s);
  if (!items.length && S.c.category) items = S.templates.filter((t) => t.category === S.c.category).slice(0, 5);
  $('#advice-hint').textContent = items.length ? `${items.length} match${items.length === 1 ? '' : 'es'}` : 'Triage the call to see matches';
  for (const t of items) list.append(adviceItem(t));
  updateSelected();
}

function adviceItem(t) {
  const sel = S.c.selectedTemplates.includes(t.id);
  return h('li', { class: 'item' },
    h('div', { class: 'item-title' }, h('span', {}, t.title), t.needs_review ? h('span', { class: 'pill pill-warn' }, 'verify') : null),
    h('div', { class: 'item-sub' }, t.summary),
    h('details', {}, h('summary', {}, 'Read full answer'), h('pre', {}, t.body),
      t.source_urls?.length ? h('p', { class: 'small' }, 'Sources: ', t.source_urls.map((u, i) => [i ? ', ' : '', h('a', { href: u, target: '_blank', rel: 'noopener noreferrer' }, new URL(u).hostname)])) : null),
    h('div', { class: 'item-actions' },
      h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: () => copy(t.sms, 'SMS copied') }, 'Copy SMS'),
      h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: () => copy(t.body, 'Email text copied') }, 'Copy email'),
      h('button', {
        class: `btn btn-sm ${sel ? 'btn-primary' : 'btn-ghost'}`, type: 'button', 'aria-pressed': String(sel),
        onclick: (e) => {
          const i = S.c.selectedTemplates.indexOf(t.id);
          if (i >= 0) S.c.selectedTemplates.splice(i, 1); else S.c.selectedTemplates.push(t.id);
          const on = i < 0;
          e.currentTarget.className = `btn btn-sm ${on ? 'btn-primary' : 'btn-ghost'}`;
          e.currentTarget.setAttribute('aria-pressed', String(on));
          e.currentTarget.textContent = on ? '✓ Added' : 'Add';
          persist();
          updateSelected();
        },
      }, sel ? '✓ Added' : 'Add'),
    ));
}

function updateSelected() {
  const n = S.c.selectedTemplates.length;
  $('#selected-count').textContent = String(n);
  $('#btn-gen-resolution').disabled = n === 0;
}

function bindResolve() {
  $('#btn-gen-resolution').addEventListener('click', async () => {
    const out = await generateDraft('resolution');
    if (out) renderDraft($('#resolution-output'), out);
  });
  $('#search-form').addEventListener('submit', (e) => { e.preventDefault(); runSearch(); });
}

function localDraft(kind) {
  // Offline fallback: stitch the selected standard responses together.
  const first = S.c.data.first_name || 'there';
  const sign = `Warm regards,\n\n${S.meta.office.signoff}\n${S.meta.office.name}`;
  if (kind === 'resolution') {
    const ts = S.c.selectedTemplates.map((id) => S.templates.find((t) => t.id === id)).filter(Boolean);
    return {
      subject: 'Information from our office',
      email: [`Hi ${first},`, 'Thanks so much for chatting with our office today. As promised, here\'s the information we went through:',
        ...ts.map((t) => `${t.title}\n${t.body}`), 'If you get stuck, just reply to this email or give us a call.', sign].join('\n\n'),
      sms: `Hi ${first}, thanks for calling. ${ts.map((t) => t.sms).join(' ')} - ${S.meta.office.signoff}`,
      engine: 'offline',
    };
  }
  return {
    subject: 'We\'ve received your enquiry',
    email: [`Hi ${first},`, 'Thanks so much for getting in touch with our office. We\'ve opened a case for you and will be in touch soon.', sign].join('\n\n'),
    sms: `Hi ${first}, thanks for calling our office. We've opened a case and will be in touch soon. - ${S.meta.office.signoff}`,
    engine: 'offline',
  };
}

async function generateDraft(kind) {
  const btn = kind === 'resolution' ? $('#btn-gen-resolution') : $('#btn-gen-ack');
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Writing…';
  try {
    const out = await api('/api/generate', {
      method: 'POST',
      body: { kind, category: cat(), data: S.c.data, notes: S.c.notes, template_ids: S.c.selectedTemplates },
    });
    S.c.draft = out.email;
    persist();
    autosave();
    return out;
  } catch (e) {
    if (e instanceof OfflineError) { toast('Offline: basic draft only'); return localDraft(kind); }
    toast(e.message);
    return null;
  } finally {
    btn.disabled = kind === 'resolution' ? S.c.selectedTemplates.length === 0 : false;
    btn.textContent = label;
  }
}

function renderDraft(box, d) {
  const phone = S.c.data.phone || '';
  const email = S.c.data.email || '';
  const subj = h('input', { value: d.subject, 'aria-label': 'Subject' });
  const body = h('textarea', { 'aria-label': 'Email body' });
  body.value = d.email;
  const sms = h('textarea', { class: 'sms', 'aria-label': 'SMS text' });
  sms.value = d.sms;
  const count = h('span', { class: 'muted small' });
  const upd = () => { const n = sms.value.length; count.textContent = `${n} characters · ${Math.ceil(n / 153) || 1} SMS`; };
  sms.addEventListener('input', upd);
  upd();
  box.replaceChildren(
    h('h3', {}, 'SMS'), sms, count,
    h('div', { class: 'row' },
      h('button', { class: 'btn btn-primary btn-block', type: 'button', onclick: () => copy(sms.value, 'SMS copied') }, 'Copy SMS'),
      h('a', { class: 'btn btn-ghost btn-block', href: '#', onclick: (e) => { e.currentTarget.href = `sms:${phone.replace(/[^\d+]/g, '')}?&body=${encodeURIComponent(sms.value)}`; } }, 'Open SMS app')),
    h('h3', {}, 'Email'), subj, body,
    h('div', { class: 'row' },
      h('button', { class: 'btn btn-primary btn-block', type: 'button', onclick: () => copy(body.value, 'Email copied') }, 'Copy email'),
      h('a', { class: 'btn btn-ghost btn-block', href: '#', onclick: (e) => { e.currentTarget.href = `mailto:${encodeURIComponent(email)}?subject=${encodeURIComponent(subj.value)}&body=${encodeURIComponent(body.value)}`; } }, 'Open mail app')),
    h('p', { class: 'muted small' }, d.engine === 'model' ? 'Polished by the drafting model: check every fact before sending.' : d.engine === 'offline' ? 'Offline draft.' : 'Template draft.'),
  );
  box.hidden = false;
}

// ----------------------------------------------------------------- search --
function updateSearchDomains() {
  const box = $('#search-domains');
  const all = S.meta.categories.flatMap((c) => c.domains);
  const uniq = [...new Set(all)];
  const scoped = S.meta.categories.find((c) => c.id === cat())?.domains || [];
  S.searchDomains = new Set(scoped);
  box.replaceChildren(...uniq.map((d) => h('button', {
    class: 'chip', type: 'button', 'aria-pressed': String(S.searchDomains.has(d)),
    onclick: (e) => {
      if (S.searchDomains.has(d)) S.searchDomains.delete(d); else S.searchDomains.add(d);
      e.currentTarget.setAttribute('aria-pressed', String(S.searchDomains.has(d)));
    },
  }, d)));
}

async function runSearch() {
  const q = $('#search-q').value.trim();
  if (!q) return;
  const box = $('#search-results');
  box.replaceChildren(h('p', { class: 'muted' }, 'Searching…'));
  try {
    const r = await api('/api/search', { method: 'POST', body: { q, category: cat(), domains: [...S.searchDomains] } });
    renderSearch(r);
  } catch (e) {
    box.replaceChildren(h('p', { class: 'alert alert-warn' }, e instanceof OfflineError ? 'Search needs a connection.' : e.message));
  }
}

function renderSearch(r) {
  const box = $('#search-results');
  box.replaceChildren();
  if (r.error) box.append(h('p', { class: 'alert alert-warn' }, r.error));
  for (const x of r.results) {
    box.append(h('div', { class: 'result' },
      h('a', { class: 'title', href: x.url, target: '_blank', rel: 'noopener noreferrer' }, x.title),
      h('div', { class: 'domain' }, x.domain),
      h('p', {}, x.snippet),
      x.phones.length ? h('div', { class: 'phones' }, x.phones.map((p) => h('a', { href: telHref(p) }, `📞 ${p}`))) : null,
      h('div', { class: 'item-actions' },
        h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: () => copy(`${x.title}\n${x.snippet}\n${x.url}`, 'Copied') }, 'Copy'),
        h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: () => copy(`${x.title}: ${x.url}`, 'Link copied') }, 'Copy link for SMS'))));
  }
  if (!r.results.length && r.links.length) {
    box.append(h('p', { class: 'muted small' }, r.provider ? 'No official results. Try:' : 'Open a site-restricted search:'),
      h('div', { class: 'phones' }, r.links.map((l) => h('a', { href: l.url, target: '_blank', rel: 'noopener noreferrer' }, `🔎 ${l.domain}`))));
  }
  if (r.directory.length) {
    box.append(h('div', { class: 'directory' }, h('h3', {}, 'Key contacts'),
      h('div', { class: 'phones' }, r.directory.map((d) => (d.phone
        ? h('a', { href: telHref(d.phone) }, `${d.name}: ${d.phone}`)
        : h('a', { href: d.url, target: '_blank', rel: 'noopener noreferrer' }, d.name))))));
  }
}

// --------------------------------------------------------------- escalate --
function fieldEl(f) {
  const v = S.c.data[f.id];
  const id = `f-${f.id}`;
  const onChange = (e) => {
    const el = e.currentTarget;
    S.c.data[f.id] = el.type === 'checkbox' ? el.checked : el.value;
    persist();
    refreshEscalate();
    autosave();
  };
  if (f.type === 'checkbox') {
    const input = h('input', { type: 'checkbox', id, onchange: onChange });
    input.checked = v === true || v === 'true';
    return h('div', { class: 'field wide', 'data-field': f.id },
      h('label', { class: 'check', for: id }, input, f.label),
      f.help ? h('span', { class: 'field-help' }, f.help) : null);
  }
  let input;
  if (f.type === 'select') {
    input = h('select', { id, onchange: onChange }, h('option', { value: '' }, 'Select…'), f.options.map((o) => h('option', { value: o }, o)));
    input.value = v || (f.id === 'state' ? 'QLD' : '');
  } else if (f.type === 'textarea') {
    input = h('textarea', { id, rows: '2', oninput: onChange });
    input.value = v || '';
  } else {
    input = h('input', {
      id, type: f.type, oninput: onChange, placeholder: f.placeholder || null,
      inputmode: f.inputmode || null, autocomplete: f.autocomplete || 'off',
    });
    input.value = v || '';
  }
  return h('div', { class: `field${f.type === 'textarea' ? ' wide' : ''}`, 'data-field': f.id },
    h('label', { class: 'label', for: id }, f.label), input,
    f.help ? h('span', { class: 'field-help' }, f.help) : null);
}

function renderForm() {
  const c = cat();
  const fields = S.meta.fields.filter((f) => f.categories.includes('*') || f.categories.includes(c));
  $('#fields-constituent').replaceChildren(...fields.filter((f) => f.group === 'constituent').map(fieldEl));
  $('#fields-matter').replaceChildren(...fields.filter((f) => f.group === 'matter').map(fieldEl));
}

function refreshEscalate() {
  const maybe = (S.c.triage?.requirements || []).filter((r) => r.maybe_in_notes).map((r) => r.key);
  const ev = evaluate(S.meta, cat(), S.c.data, maybe);
  const pct = Math.round(ev.completeness * 100);
  $('#completeness-pill').textContent = `${pct}% captured`;
  $('#completeness-pill').className = `pill ${ev.ready ? 'pill-ok' : 'pill-warn'}`;
  const bar = $('#completeness-bar');
  bar.style.width = `${pct}%`;
  bar.classList.toggle('done', ev.missing.length === 0);

  const list = $('#ask-list');
  list.replaceChildren(...ev.missing
    .sort((a, b) => a.priority - b.priority)
    .map((r) => h('li', { class: `ask-item p${r.priority}`, tabindex: '0', role: 'button', onclick: () => focusField(r.fields[0]), onkeydown: (e) => { if (e.key === 'Enter') focusField(r.fields[0]); } },
      h('span', { class: 'tick', 'aria-hidden': 'true' }),
      h('div', {},
        h('strong', {}, r.label, r.priority === 1 ? ' *' : ''),
        h('span', { class: 'say' }, `“${r.ask}”`),
        r.maybe_in_notes ? h('span', { class: 'pill pill-warn maybe' }, 'Mentioned in notes: confirm') : null))));
  $('#ask-done').hidden = ev.missing.length > 0;
  renderExtracted();
  refreshJotform(ev);
}

function focusField(fid) {
  const wrap = document.querySelector(`[data-field="${fid}"]`);
  if (!wrap) return;
  const input = wrap.querySelector('input, select, textarea');
  wrap.scrollIntoView({ behavior: 'smooth', block: 'center' });
  wrap.classList.add('flash');
  setTimeout(() => wrap.classList.remove('flash'), 1500);
  input?.focus({ preventScroll: true });
}

function renderExtracted() {
  const ex = Object.entries(S.c.triage?.extracted || {}).filter(([k]) => !S.c.data[k]);
  const card = $('#extracted');
  card.hidden = ex.length === 0;
  const label = (k) => S.meta.fields.find((f) => f.id === k)?.label || k;
  $('#extracted-list').replaceChildren(...ex.map(([k, v]) => h('button', {
    class: 'chip', type: 'button', onclick: () => applyExtracted([[k, v]]),
  }, `${label(k)}: ${k === 'consent_signed' ? 'yes' : v}`)));
}

function applyExtracted(pairs) {
  for (const [k, v] of pairs) S.c.data[k] = k === 'consent_signed' ? v === 'true' || v === true : v;
  persist();
  renderForm();
  refreshEscalate();
  autosave();
}

function refreshJotform(ev) {
  if (!S.meta) return;
  ev = ev || evaluate(S.meta, cat(), S.c.data);
  const j = buildJotformUrl(S.meta, cat(), S.c.data, S.c.notes, S.c.triage?.urgency || '');
  $('#btn-jotform').href = j.url;
  const warn = [];
  const blocking = ev.missing.filter((r) => r.priority === 1).map((r) => r.label);
  if (blocking.length) warn.push(`Still missing: ${blocking.join(', ')}.`);
  if (j.truncated) warn.push('Notes were too long for the link: use “Copy case notes” and paste them in.');
  const w = $('#jotform-warning');
  w.textContent = warn.join(' ');
  w.hidden = warn.length === 0;
}

function bindEscalate() {
  $('#btn-apply-extracted').addEventListener('click', () => applyExtracted(Object.entries(S.c.triage?.extracted || {}).filter(([k]) => !S.c.data[k])));
  $('#btn-jotform').addEventListener('click', () => { S.c.mode = 'escalate'; saveCaseNow(S.c); syncCase(); });
  $('#btn-copy-casenotes').addEventListener('click', () => {
    copy(buildJotformUrl(S.meta, cat(), S.c.data, S.c.notes, S.c.triage?.urgency || '').details, 'Case notes copied');
  });
  $('#btn-mark-lodged').addEventListener('click', () => { S.c.status = 'lodged'; persist(); syncCase(); toast('Marked as lodged'); });
  $('#btn-gen-ack').addEventListener('click', async () => {
    const out = await generateDraft('acknowledgement');
    if (out) renderDraft($('#ack-output'), out);
  });
}

// ------------------------------------------------------------------- tabs --
function setView(v) {
  S.view = v;
  document.querySelectorAll('.view').forEach((el) => { el.hidden = el.dataset.view !== v; });
  document.querySelectorAll('.tab').forEach((t) => {
    const on = t.dataset.target === v;
    t.classList.toggle('active', on);
    if (on) t.setAttribute('aria-current', 'page'); else t.removeAttribute('aria-current');
  });
  $('#intake').hidden = !(v === 'resolve' || v === 'escalate');
  if (v === 'escalate') $('#escalate-dot').hidden = true;
  if (v === 'recent') renderRecent();
  if (v === 'library') loadTemplates().then(renderLibrary);
  window.scrollTo({ top: 0 });
}

function bindTabs() {
  document.querySelectorAll('.tab').forEach((t) => t.addEventListener('click', () => setView(t.dataset.target)));
}

// ---------------------------------------------------------------- library --
function bindLibrary() {
  const sel = $('#lib-category');
  sel.replaceChildren(h('option', { value: '' }, 'All categories'), S.meta.categories.map((c) => h('option', { value: c.id }, c.label)));
  $('#t-category').replaceChildren(...S.meta.categories.map((c) => h('option', { value: c.id }, c.label)));
  sel.addEventListener('change', renderLibrary);
  $('#lib-q').addEventListener('input', debounce(renderLibrary, 150));
  $('#btn-lib-new').addEventListener('click', () => openEditor(null));
  $('#t-sms').addEventListener('input', () => { $('#t-sms-count').textContent = `${$('#t-sms').value.length} characters`; });
  $('#tmpl-form').addEventListener('submit', saveTemplate);
  $('#btn-tmpl-delete').addEventListener('click', deleteTemplate);
}

function renderLibrary() {
  const q = $('#lib-q').value.trim().toLowerCase();
  const c = $('#lib-category').value;
  const items = S.templates.filter((t) => (!c || t.category === c)
    && (!q || `${t.title} ${t.summary} ${t.body} ${t.tags.join(' ')}`.toLowerCase().includes(q)));
  $('#lib-list').replaceChildren(...items.map((t) => h('li', { class: 'item' },
    h('div', { class: 'item-title' }, h('span', {}, t.title),
      t.needs_review ? h('span', { class: 'pill pill-warn' }, 'needs review') : h('span', { class: 'pill pill-ok' }, `reviewed ${t.last_reviewed || ''}`)),
    h('div', { class: 'item-sub' }, `${catLabel(t.category)} · ${t.summary}`),
    h('details', {}, h('summary', {}, 'Preview'), h('pre', {}, t.body)),
    h('div', { class: 'item-actions' },
      h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: () => copy(t.sms, 'SMS copied') }, 'Copy SMS'),
      h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: () => copy(t.body, 'Copied') }, 'Copy'),
      h('button', {
        class: 'btn btn-sm btn-ghost', type: 'button',
        onclick: () => {
          if (!S.c.selectedTemplates.includes(t.id)) S.c.selectedTemplates.push(t.id);
          if (!(S.c.triage?.suggested_templates || []).some((s) => s.id === t.id)) {
            S.c.triage = S.c.triage || { suggested_templates: [] };
            S.c.triage.suggested_templates = [...(S.c.triage.suggested_templates || []), t];
          }
          persist();
          renderAdvice();
          toast('Added to draft');
        },
      }, 'Insert into draft'),
      h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: () => openEditor(t) }, 'Edit')))));
  if (!items.length) $('#lib-list').append(h('li', { class: 'muted' }, 'No matching responses.'));
}

let editing = null;
function openEditor(t) {
  editing = t;
  $('#tmpl-dialog-title').textContent = t ? 'Edit response' : 'New response';
  $('#t-title').value = t?.title || '';
  $('#t-category').value = t?.category || cat();
  $('#t-tags').value = (t?.tags || []).join(', ');
  $('#t-summary').value = t?.summary || '';
  $('#t-sms').value = t?.sms || '';
  $('#t-body').value = t?.body || '';
  $('#t-sources').value = (t?.source_urls || []).join('\n');
  $('#t-sms-count').textContent = `${$('#t-sms').value.length} characters`;
  $('#btn-tmpl-delete').hidden = !t;
  $('#tmpl-dialog').showModal();
}

async function saveTemplate(e) {
  if (e.submitter?.value !== 'save') return;
  e.preventDefault();
  const body = {
    title: $('#t-title').value.trim(),
    category: $('#t-category').value,
    tags: $('#t-tags').value.split(',').map((s) => s.trim()).filter(Boolean),
    summary: $('#t-summary').value.trim(),
    sms: $('#t-sms').value.trim(),
    body: $('#t-body').value.trim(),
    source_urls: $('#t-sources').value.split('\n').map((s) => s.trim()).filter((s) => /^https?:\/\//.test(s)),
  };
  if (!body.title) { $('#t-title').focus(); return; }
  try {
    if (editing) await api(`/api/templates/${editing.id}`, { method: 'PATCH', body });
    else await api('/api/templates', { method: 'POST', body });
    $('#tmpl-dialog').close();
    await loadTemplates();
    renderLibrary();
    renderAdvice();
    toast('Saved');
  } catch (err) {
    toast(err instanceof OfflineError ? 'Editing needs a connection' : err.message);
  }
}

async function deleteTemplate() {
  if (!editing || !window.confirm(`Delete “${editing.title}”?`)) return;
  try {
    await api(`/api/templates/${editing.id}`, { method: 'DELETE' });
    $('#tmpl-dialog').close();
    await loadTemplates();
    renderLibrary();
    toast('Deleted');
  } catch (err) {
    toast(err instanceof OfflineError ? 'Deleting needs a connection' : err.message);
  }
}

// ----------------------------------------------------------------- recent --
function hasContent(c) {
  return Boolean((c.notes || '').trim() || Object.entries(c.data).some(([k, v]) => k !== 'state' && v));
}

async function syncCase() {
  if (!S.online || !hasContent(S.c)) return;
  try {
    await api('/api/cases', {
      method: 'PUT',
      body: {
        client_id: S.c.client_id, category: cat(), mode: S.c.mode === 'escalate' ? 'escalate' : 'resolve',
        data: S.c.data, notes: S.c.notes, draft: S.c.draft || '', status: S.c.status || 'open',
      },
    });
  } catch { /* stays in local storage; retried on next change */ }
}
const autosave = debounce(syncCase, 2000);

async function renderRecent() {
  const list = $('#recent-list');
  list.replaceChildren(h('li', { class: 'muted' }, 'Loading…'));
  try {
    const rows = await api('/api/cases');
    list.replaceChildren(...rows.map((r) => h('li', { class: 'item' },
      h('div', { class: 'item-title' }, h('span', {}, r.label),
        h('span', { class: `pill ${r.status === 'lodged' ? 'pill-ok' : 'pill-warn'}` }, r.status)),
      h('div', { class: 'item-sub' }, `${new Date(r.updated_at).toLocaleString('en-AU', { dateStyle: 'medium', timeStyle: 'short' })} · ${r.mode}`),
      h('div', { class: 'item-sub' }, (r.notes || '').slice(0, 140)),
      h('div', { class: 'item-actions' },
        h('button', { class: 'btn btn-sm btn-primary', type: 'button', onclick: () => openCase(r) }, 'Open'),
        h('button', {
          class: 'btn btn-sm btn-danger', type: 'button',
          onclick: async () => {
            if (!window.confirm('Delete this saved call?')) return;
            try { await api(`/api/cases/${encodeURIComponent(r.client_id)}`, { method: 'DELETE' }); renderRecent(); } catch (e) { toast(e.message); }
          },
        }, 'Delete')))));
    if (!rows.length) list.append(h('li', { class: 'muted' }, 'No saved calls yet.'));
  } catch (e) {
    list.replaceChildren(h('li', { class: 'muted' }, e instanceof OfflineError ? 'Recent calls need a connection.' : e.message));
  }
}

async function openCase(r) {
  await syncCase();
  S.c = { ...newCase(), client_id: r.client_id, category: r.category, notes: r.notes, data: { state: 'QLD', ...r.data }, mode: r.mode, status: r.status, draft: r.draft };
  saveCaseNow(S.c);
  restoreCase();
  setView(r.mode === 'escalate' ? 'escalate' : 'resolve');
}

async function startNewCase() {
  if (hasContent(S.c) && !window.confirm('Start a new call? The current one is saved to Recent.')) return;
  await syncCase();
  S.c = newCase();
  saveCaseNow(S.c);
  restoreCase();
  $('#search-q').value = '';
  $('#search-results').replaceChildren();
  $('#resolution-output').hidden = true;
  $('#ack-output').hidden = true;
  setView('resolve');
  $('#notes').focus();
}

function restoreCase() {
  $('#notes').value = S.c.notes || '';
  $('#tfn-warning').hidden = !hasTfn(S.c.notes);
  renderChips();
  renderTriage();
  renderForm();
  renderAdvice();
  refreshEscalate();
  updateSearchDomains();
}

document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') { saveCaseNow(S.c); syncCase(); } });
boot();
