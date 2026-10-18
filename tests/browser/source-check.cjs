// Mock source automation in Settings and the Case watch update: desktop 1440 + mobile 390, keyboard, error and duplicate states.
// TEST stack (3002); fresh expiring sample workspace deleted at the end. Synthetic mock sources only.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { execFileSync } = require('node:child_process');
const base = process.env.TEST_WEB_URL || 'http://localhost:3002';
const DB = process.env.TEST_DB_CONTAINER || 'trialops-release-test-db-1';
const shots = process.env.SHOT_DIR || 'artifacts/source-screenshots';
const sql = q => execFileSync('docker', ['exec', '-i', DB, 'psql', '-U', 'trialops', '-d', 'trialops', '-At', '-c', q]).toString().trim();
(async () => {
  fs.mkdirSync(shots, { recursive: true });
  const options = { headless: true }; if (process.env.CHROMIUM_PATH) options.executablePath = process.env.CHROMIUM_PATH;
  const browser = await chromium.launch(options), errors = [];
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  page.on('pageerror', e => errors.push(e.stack || e.message)); page.on('console', m => { if (m.type() === 'error') console.log('CONSOLE', m.text().slice(0, 300)); });
  let W = null; const step = s => console.log('OK:', s);
  const call = (path, body) => page.evaluate(async ([p, b]) => { const r = await fetch('/api' + p, { method: b ? 'POST' : 'GET', headers: { 'Content-Type': 'application/json' }, body: b ? JSON.stringify(b) : undefined }); return { status: r.status, body: await r.json().catch(() => ({})) }; }, [path, body]);
  const noOverflow = async n => assert((await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)) <= 1, n + ' overflows horizontally');
  try {
    await page.goto(base + '/'); await page.getByRole('button', { name: 'Explore a sample case', exact: true }).first().click(); await page.waitForURL('**/workspace'); await page.waitForLoadState('networkidle');
    W = (await (await page.request.get(base + '/api/auth/me')).json()).workspace_id;
    sql(`INSERT INTO cases(workspace_id,id,study_id,site_id,title,description,category,priority,status) VALUES('${W}','SRC-UI','CT-204','SITE-104','Source automation case','Synthetic.','document_workflow','medium','open')`);
    const job = (await call('/cases/SRC-UI/investigate', {})).body; for (let k = 0; k < 120; k++) { const st = (await call('/jobs/' + job.id)).body; if (st.status === 'failed') throw new Error(st.error); if (st.status === 'completed') break; await page.waitForTimeout(1000); }
    assert.equal((await call('/cases/SRC-UI/journey/subject', { id: crypto.randomUUID(), expected_rev: 0, document_system: 'mock-upload-portal', document_ref: 'DOC-5001', document_version: '2', destination_system: 'mock-binder-hub', binder_ref: 'BND-77' })).status, 200);

    // Settings: compact owner-only configuration
    await page.goto(base + '/workspace/settings'); await page.waitForLoadState('networkidle');
    await page.getByRole('button', { name: 'Data policy' }).click();
    const sec = page.getByRole('region', { name: 'Document-processing sources' }); await sec.waitFor();
    assert.match(await sec.innerText(), /synthetic mock sources only/i); assert.match(await sec.innerText(), /No real vendor account is connected/);
    await sec.getByLabel('Source name').fill('Mock portal (demo)'); await sec.getByRole('button', { name: 'Add mock source' }).click();
    await sec.getByText(/Source key \(shown once\)/).waitFor(); await sec.getByText('Enabled · connected').waitFor();
    assert.match(await sec.innerText(), /Last successful collection: none yet/);
    const draft = sec.getByLabel(/Prepare an unsent draft request/); assert.equal(await draft.isChecked(), false, 'draft preparation defaults to off'); step('owner configuration: name, status, last collection, key once, draft preparation off by default');
    await sec.scrollIntoViewIfNeeded(); await sec.screenshot({ path: shots + '/settings-1440.png' });

    // error state: unknown case; then a real delivery
    await sec.getByText('Send a synthetic test event').click();
    await sec.getByLabel(/Case ID/).fill('NO-SUCH-CASE'); await sec.getByRole('button', { name: 'Send test event' }).click();
    await sec.getByRole('alert').waitFor(); step('error state shown for an unknown case; nothing created');
    await sec.getByLabel(/Case ID/).fill('SRC-UI'); await sec.getByRole('button', { name: 'Send test event' }).click();
    await sec.getByText(/Delivery accepted/).waitFor();
    for (let k = 0; k < 60 && sql(`select status from source_events where workspace_id='${W}'`) !== 'processed'; k++) await page.waitForTimeout(1000);
    assert.equal(sql(`select status from source_events where workspace_id='${W}'`), 'processed');
    await sec.getByLabel('Scenario').selectOption('duplicate_delivery'); await sec.getByRole('button', { name: 'Send test event' }).click(); await sec.getByText(/Delivery duplicate/).waitFor();
    await sec.getByText('Recent events and counts').click(); assert.match(await sec.innerText(), /1 duplicate deliveries|1 event received/); step('delivery processed in the background; duplicate delivery reported, not re-processed');

    // Case watch update
    await page.goto(base + '/workspace/cases/SRC-UI'); await page.waitForLoadState('networkidle');
    const watch = page.locator('.case-watch'); await watch.waitFor({ timeout: 20000 }).catch(async e => { console.log(page.url() + ' | ' + (await page.locator('body').innerText()).slice(0, 500)); console.log(errors.join(' ; ').slice(0, 800)); throw e; });
    const head = watch.locator('.source-headline'); await head.waitFor();
    assert.match(await head.innerText(), /^New evidence received\. (One|Two|Three|Four|Five|Six|Seven|Eight|Nine|\d+) checks? updated\. Review changes\.$/);
    const txt = await watch.innerText();
    for (const t of ['Which checks changed', 'Still unknown or conflicting', 'Next action', 'Binder visibility: unknown']) assert(txt.includes(t), 'missing: ' + t);
    assert(!/resolved the case|case is resolved|root cause is/i.test(txt.replace('does not establish root cause or resolution', '')), 'must not imply resolution');
    const det = watch.getByText('Before/after evidence references and source details'); assert.equal(await watch.getByText(/^Before$/).first().isVisible(), false, 'references are on demand'); await det.click();
    await watch.getByText('After', { exact: true }).waitFor(); assert.match(await watch.innerText(), /Synthetic mock source; not a real integration/); step('update shows what changed, which checks, what remains unknown and one next action; references on demand');
    await watch.screenshot({ path: shots + '/update-1440.png' });
    // keyboard: reach and activate Mark reviewed
    const rv = watch.getByRole('button', { name: 'Mark reviewed' }); await rv.focus(); assert(await rv.evaluate(el => el === document.activeElement)); await page.keyboard.press('Enter');
    for (let k = 0; k < 20 && sql(`select count(*) from case_events where workspace_id='${W}' and event_type='source_update_reviewed'`) !== '1'; k++) await page.waitForTimeout(300);
    assert.equal(sql(`select count(*) from case_events where workspace_id='${W}' and event_type='source_update_reviewed'`), '1'); step('keyboard activation records one reviewer action');
    assert.equal(sql(`select status from cases where workspace_id='${W}' and id='SRC-UI'`), 'open'); assert.equal(sql(`select count(*) from information_requests where workspace_id='${W}' and status<>'draft'`), '0');

    // no-draft explanation: store the exact reason the worker writes for an existing equivalent request on this synthetic update, then check the Case watch rendering
    const reason = 'A request for the suggested check already exists; no new draft was prepared.';
    sql(`update case_watch_updates set detail=jsonb_set(detail,'{draft}','{"state":"not_prepared","reason":"${reason}"}') where workspace_id='${W}' and source_event_id is not null`);
    await page.reload(); await page.waitForLoadState('networkidle'); await watch.waitFor();
    assert((await watch.innerText()).includes('No draft prepared: ' + reason), 'no-draft explanation visible at 1440'); assert(!/An unsent draft request was prepared/.test(await watch.innerText())); step('no-draft explanation shown in Case watch (1440)');

    // mobile
    await page.setViewportSize({ width: 390, height: 844 }); await page.waitForTimeout(300); await noOverflow('case 390'); await watch.screenshot({ path: shots + '/update-390.png' }); assert((await watch.innerText()).includes('No draft prepared: ' + reason), 'no-draft explanation visible at 390'); step('no-draft explanation shown in Case watch (390)');
    await page.goto(base + '/workspace/settings'); await page.waitForLoadState('networkidle'); await page.getByRole('button', { name: 'Data policy' }).click(); await noOverflow('settings 390');
    await page.getByRole('region', { name: 'Document-processing sources' }).screenshot({ path: shots + '/settings-390.png' }); step('no horizontal overflow at 390px');
    await page.emulateMedia({ reducedMotion: 'reduce' }); assert.equal(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches), true);
    // non-owner sees no configuration
    sql(`update memberships set role='reviewer' where workspace_id='${W}'`); await page.reload(); await page.waitForLoadState('networkidle');
    assert.equal(await page.getByRole('region', { name: 'Document-processing sources' }).count(), 0); step('configuration hidden for non-owners');
    assert.deepEqual(errors, [], errors.join('; '));
    console.log('PASS: source automation browser check');
  } finally { if (W) sql(`DELETE FROM workspaces WHERE id='${W}'`); await browser.close(); }
})().catch(e => { console.error('FAIL:', e); process.exit(1); });
