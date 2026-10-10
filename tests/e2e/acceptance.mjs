// Browser acceptance scenarios (brief section 10) against a running ConstitBrief server.
//
//   BASE_URL=http://localhost:8787 USER_NAME=<user> PASS=<password> node tests/e2e/acceptance.mjs [screenshot-dir]
//
// If Playwright isn't resolvable from this folder, point PLAYWRIGHT_MODULE at its index.mjs.
// Jotform is never contacted: requests to form.jotform.com are intercepted with a stub page.
const pw = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { chromium } = pw.default || pw;

const BASE = process.env.BASE_URL || 'http://localhost:8799';
const SHOTS = process.argv[2] || null;
const results = [];
let page;

async function scenario(name, fn) {
  const t0 = Date.now();
  try {
    await fn();
    results.push({ name, ok: true, ms: Date.now() - t0 });
  } catch (e) {
    results.push({ name, ok: false, ms: Date.now() - t0, error: String(e.message || e).split('\n')[0] });
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/FAIL-${name.replace(/\W+/g, '_')}.png`, fullPage: true }).catch(() => {});
  }
}
const expect = (cond, msg) => { if (!cond) throw new Error(msg); };
const shot = (n) => (SHOTS ? page.screenshot({ path: `${SHOTS}/${n}.png`, fullPage: false }) : null);

async function typeNotes(text, delay = 0) {
  await page.click('#notes');
  await page.keyboard.type(text, { delay });
}
async function waitAnalysed() {
  await page.waitForFunction(() => document.querySelector('#analysis-status')?.dataset.state === 'ok', null, { timeout: 8000 });
}
async function newInteraction() {
  page.once('dialog', (d) => d.accept());
  await page.click('#btn-new');
  await page.waitForFunction(() => document.querySelector('#notes').value === '');
}
async function fieldValue(id) { return page.inputValue(`#fd-${id}`); }

const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 } });
await ctx.route('https://form.jotform.com/**', (r) => r.fulfill({ status: 200, contentType: 'text/html', body: '<title>Jotform stub</title>stub' }));
page = await ctx.newPage();
const consoleErrors = [];
page.on('pageerror', (e) => consoleErrors.push(e.message));

await scenario('Sign-in required before any case information', async () => {
  await page.goto(BASE);
  await page.waitForSelector('#login-view:not([hidden])');
  const r = await page.evaluate(() => fetch('/api/interactions').then((x) => x.status));
  expect(r === 401, `unauthenticated API returned ${r}`);
  await page.fill('#login-username', process.env.USER_NAME || 'jo');
  await page.fill('#login-password', process.env.PASS || 'correct-horse-1');
  await page.click('#login-form button[type=submit]');
  await page.waitForSelector('#app-view:not([hidden])');
});

await scenario('Sporting club grant request plus invitation', async () => {
  await typeNotes('President of a local sporting club called about funding for equipment and wants Julie-Ann at their presentation night on 14 November.');
  await waitAnalysed();
  const types = await page.textContent('#sec-types');
  expect(/Grant assistance/.test(types) && /Event invitation/.test(types), `types: ${types}`);
  expect(/Community team/.test(await page.textContent('#sec-team')), 'team not Community');
  const q = await page.textContent('#sec-questions');
  expect(/organisation|event/i.test(q), `questions: ${q}`);
  await page.click('#tab-handoff');
  const cards = await page.locator('.handoff').count();
  expect(cards === 2, `expected 2 planned handoffs, got ${cards}`);
  await shot('01-sporting-club');
  await page.click('#tab-assistant');
});

await scenario('Rapid typing and delayed responses: stale analysis discarded, focus kept', async () => {
  await newInteraction();
  let n = 0;
  await page.route('**/api/analyse', async (route) => {
    n += 1;
    if (n === 1) await new Promise((r) => setTimeout(r, 2500)); // first response arrives last
    await route.continue();
  });
  await typeNotes('Mum got a letter from Centrelink');
  await page.waitForTimeout(800); // first analysis starts (slow)
  await typeNotes('. Actually it is about her NDIS plan being cut.', 15);
  await page.waitForTimeout(3500);
  const focused = await page.evaluate(() => document.activeElement?.id);
  expect(focused === 'notes', `focus moved to ${focused}`);
  const types = await page.textContent('#sec-types');
  expect(/NDIS/.test(types), `final analysis not applied: ${types}`);
  await page.unroute('**/api/analyse');
});

await scenario('NDIS enquiry with incomplete details', async () => {
  await newInteraction();
  await typeNotes("Caller's NDIS plan was cut at reassessment and she wants it reviewed.");
  await waitAnalysed();
  expect(/Constituent team/.test(await page.textContent('#sec-team')), 'team');
  const ready = await page.textContent('#sec-ready');
  expect(/Mandatory: Name, Address/.test(ready), `readiness: ${ready}`);
  expect((await fieldValue('ndis_number')) === '', 'NDIS number invented');
  await shot('02-ndis-incomplete');
});

await scenario('Immigration enquiry: identifiers stay visibly missing, not compulsory', async () => {
  await newInteraction();
  await typeNotes('Partner visa lodged two years ago, still waiting. Has not received an acknowledgement.');
  await waitAnalysed();
  await page.click('#checklist-details summary');
  const ck = await page.textContent('#sec-checklist');
  expect(/DHA reference \(optional\)/.test(ck) && /Suggested prompts/.test(ck), `checklist: ${ck}`);
  const ready = await page.textContent('#sec-ready');
  expect(!/DHA reference/.test(ready.split('Could improve')[0]), 'DHA reference treated as mandatory');
  const consentTxt = await page.textContent('#sec-checklist');
  expect(/Consent/.test(consentTxt), 'consent prompt missing');
  expect((await fieldValue('consent_status')) === '', 'consent inferred');
});

await scenario('Journalist with a deadline', async () => {
  await newInteraction();
  await typeNotes('Journalist from the Courier-Mail wants comment on the hospital funding story, deadline 3pm today.');
  await waitAnalysed();
  expect(/Comms team/.test(await page.textContent('#sec-team')), 'team not Comms');
  const dates = await page.textContent('#sec-dates');
  expect(/Stated deadline/.test(dates) && /3pm today/.test(dates), `dates: ${dates}`);
  await shot('03-journalist');
});

await scenario('General administrative enquiry', async () => {
  await newInteraction();
  await typeNotes('Wants to know the office opening hours.');
  await waitAnalysed();
  expect(/Administration/.test(await page.textContent('#sec-team')), 'team not Administration');
  await page.click('#tab-handoff');
  expect(/Help with another Issue/.test(await page.textContent('#handoff-list')), 'general intake option');
  await page.click('#tab-assistant');
});

await scenario('Parliamentary / ministerial request: staff-reviewed referral', async () => {
  await newInteraction();
  await typeNotes('Wants Julie-Ann to ask a question in parliament about aircraft noise and write to the minister for infrastructure.');
  await waitAnalysed();
  const types = await page.textContent('#sec-types');
  expect(/Ministerial referral/.test(types) && /Parliamentary matter/.test(types), types);
  expect(/staff to decide/i.test(await page.textContent('#sec-team')), 'ownership should be staff decision');
  expect(/staff approval/i.test(await page.textContent('#sec-actions')), 'referral approval action');
});

await scenario('Ambiguous or conflicting notes', async () => {
  await newInteraction();
  await typeNotes('Called about a problem, not sure what yet. Gave number 0412 345 678, then said 0498 765 432.');
  await waitAnalysed();
  expect(/uncertain/i.test(await page.textContent('#sec-alerts')), 'uncertainty not flagged');
  expect(/more than one Phone/.test(await page.textContent('#sec-alerts')), 'conflict not shown');
  expect(/main thing|Confirm/i.test(await page.textContent('#sec-questions')), 'no clarification question');
  await page.selectOption('#add-type', 'services_australia');
  await waitAnalysed();
  expect(/Constituent team/.test(await page.textContent('#sec-team')), 'manual ownership not applied');
});

await scenario('Staff correction followed by more typing', async () => {
  await newInteraction();
  await typeNotes('Centrelink stopped Age Pension. Phone 0412 345 678.');
  await waitAnalysed();
  await page.click('#sec-details .prop button:has-text("Use")');
  await waitAnalysed();
  await page.fill('#fd-phone', '0499 999 999');
  await waitAnalysed();
  await typeNotes(' She also mentioned her husband.');
  await waitAnalysed();
  expect((await fieldValue('phone')) === '0499 999 999', 'staff value overwritten');
  expect(/Notes say 0412345678 but the record has 0499 999 999/.test(await page.textContent('#sec-alerts')), 'contradiction not raised');
});

await scenario('Mandatory Jotform field missing blocks submission', async () => {
  await newInteraction();
  await typeNotes('Needs help with an ATO tax debt payment plan.');
  await waitAnalysed();
  await page.click('#tab-handoff');
  await page.click('.handoff button:has-text("Review mapping")');
  await page.waitForSelector('.handoff .map-table');
  expect(/Name: First name is required by the form/.test(await page.textContent('.handoff')), 'missing requirement not explained');
  expect(await page.isDisabled('.handoff button:has-text("Open Jotform to submit")'), 'submit not blocked');
  await shot('04-blocked');
});

await scenario('Valid staff-approved submission maps values; retry does not duplicate', async () => {
  await page.click('#tab-assistant');
  for (const [f, v] of [['first_name', 'Test'], ['last_name', 'Synthetic'], ['address_line1', '1 Example St'], ['suburb', 'Sunnybank']]) {
    await page.fill(`#fd-${f}`, v);
  }
  await page.fill('#sum-issue', 'Synthetic test record: ATO payment plan enquiry.');
  await waitAnalysed();
  await page.click('#tab-handoff');
  await page.click('.handoff button:has-text("Review")');
  await page.waitForFunction(() => !document.querySelector('.handoff button.btn-primary:last-of-type')?.disabled);
  const table = await page.textContent('.map-table');
  expect(/Help with an ATO issue/.test(table) && /Synthetic/.test(table) && /ConstitBrief ref: CB-/.test(table), 'mapping wrong');
  const [popup] = await Promise.all([ctx.waitForEvent('page'), page.click('.handoff button:has-text("Open Jotform to submit")')]);
  await popup.waitForURL(/jotform/, { timeout: 5000 });
  const url = popup.url();
  expect(url.startsWith('https://form.jotform.com/252413844700855'), url);
  expect(!/Synthetic|Example|payment/.test(decodeURIComponent(url)), `sensitive data in URL: ${url}`);
  await popup.close();
  await page.waitForSelector('.handoff:has-text("NOT confirmed")');
  page.once('dialog', (d) => d.accept('')); // optional submission id prompt
  await page.click('.handoff button:has-text("Yes, submitted")');
  await page.waitForSelector('.handoff:has-text("Submitted (reported by staff)")');
  // Retry: preparing the same option again must warn about duplicates (declined here).
  let warned = false;
  page.once('dialog', (d) => { warned = /duplicate/i.test(d.message()); d.dismiss(); });
  await page.click('.handoff button:has-text("Review")');
  await page.waitForTimeout(600);
  expect(warned, 'no duplicate warning');
  const rows = await page.evaluate(async () => {
    const list = await fetch('/api/interactions').then((r) => r.json());
    return list.length;
  });
  expect(rows >= 1, 'interactions');
  await shot('05-submitted');
});

await scenario('AI unavailable: manual intake and handoff continue', async () => {
  await newInteraction();
  await page.route('**/api/analyse', (r) => r.abort());
  try {
  await page.click('#tab-assistant');
  await typeNotes('Manual mode test: constituent needs help with a flag for their school.');
  await page.waitForFunction(() => document.querySelector('#analysis-status')?.dataset.state === 'error', null, { timeout: 5000 });
  expect((await page.inputValue('#notes')).includes('Manual mode test'), 'notes lost');
  await page.selectOption('#add-type', 'flag');
  await page.waitForTimeout(200);
  await page.click('#tab-handoff');
  expect(/Request a Flag/.test(await page.textContent('#handoff-list')), 'manual handoff not available');
  } finally {
    await page.unroute('**/api/analyse');
    await page.click('#tab-assistant');
  }
});

await scenario('New interaction clears the previous person', async () => {
  await page.fill('#fd-first_name', 'Previous');
  await page.waitForTimeout(300);
  await page.click('#tab-handoff');
  page.once('dialog', (d) => d.accept());
  await page.click('#btn-finish');
  await page.waitForFunction(() => document.querySelector('#notes').value === '');
  await page.click('#tab-assistant');
  const firstName = await page.$('#fd-first_name') ? await fieldValue('first_name') : '';
  expect(firstName === '', 'previous name still shown');
  const html = await page.content();
  expect(!html.includes('Previous') && !html.includes('Manual mode test'), 'previous context leaked');
  const stored = await page.evaluate(() => sessionStorage.getItem('cb.current') || '');
  expect(!stored.includes('Manual mode test'), 'previous notes in session storage');
});

await scenario('Mobile: panel switching preserves notes', async () => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.click('#tab-notes');
  await typeNotes('Mobile check: Centrelink payment stopped.');
  await page.click('#tab-assistant');
  await page.click('#tab-notes');
  expect((await page.inputValue('#notes')).includes('Mobile check'), 'notes lost on panel switch');
  await waitAnalysed();
  await page.click('#tab-assistant');
  await shot('06-mobile-assistant');
  await page.setViewportSize({ width: 1360, height: 900 });
});

await scenario('Latency: useful update within 2 s of a typing pause', async () => {
  await newInteraction();
  await typeNotes('Constituent waiting on aged care assessment from My Aged Care');
  const t0 = Date.now();
  await waitAnalysed();
  const ms = Date.now() - t0;
  expect(ms < 2000, `took ${ms} ms`);
  const status = await page.textContent('#analysis-status');
  console.log(`  latency: ${ms} ms after typing stopped (debounce 650 ms included); status "${status.trim()}"`);
});

await browser.close();
const width = Math.max(...results.map((r) => r.name.length));
for (const r of results) console.log(`${r.ok ? 'PASS' : 'FAIL'}  ${r.name.padEnd(width)}  ${String(r.ms).padStart(5)} ms${r.error ? `  -> ${r.error}` : ''}`);
if (consoleErrors.length) console.log('Page errors:', consoleErrors);
const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed}/${results.length} scenarios passed`);
process.exit(failed || consoleErrors.length ? 1 : 0);
