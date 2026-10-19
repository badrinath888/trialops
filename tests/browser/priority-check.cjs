// Suggested request order in the Document journey collection plan: desktop 1440 + mobile 390, keyboard, form-state preservation, stale/refresh, override, draft from a suggestion.
// TEST stack (3002); fresh expiring sample workspace deleted at the end.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { execFileSync } = require('node:child_process');
const base = require('./target.cjs')();
const DB = process.env.TEST_DB_CONTAINER || 'trialops-release-test-db-1';
const shots = process.env.SHOT_DIR || 'artifacts/priority-screenshots';
const sql = q => execFileSync('docker', ['exec', '-i', DB, 'psql', '-U', 'trialops', '-d', 'trialops', '-At', '-c', q]).toString().trim();
const __memo = {}; const ago = h => (__memo[h] ||= new Date(Date.now() - h * 3600e3));
(async () => {
  fs.mkdirSync(shots, { recursive: true });
  const options = { headless: true }; if (process.env.CHROMIUM_PATH) options.executablePath = process.env.CHROMIUM_PATH;
  const browser = await chromium.launch(options), errors = [];
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  page.on('pageerror', e => errors.push(e.stack || e.message));
  let W = null; const step = s => console.log('OK:', s);
  const call = (path, body) => page.evaluate(async ([p, b]) => { const r = await fetch('/api' + p, { method: b ? 'POST' : 'GET', headers: { 'Content-Type': 'application/json' }, body: b ? JSON.stringify(b) : undefined }); return { status: r.status, body: await r.json().catch(() => ({})) }; }, [path, body]);
  const noOverflow = async n => assert((await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)) <= 1, n + ' overflows horizontally');
  try {
    await page.goto(base + '/'); await page.getByRole('button', { name: 'Explore a sample case', exact: true }).first().click(); await page.waitForURL('**/workspace'); await page.waitForLoadState('networkidle');
    W = (await (await page.request.get(base + '/api/auth/me')).json()).workspace_id;
    sql(`INSERT INTO cases(workspace_id,id,study_id,site_id,title,description,category,priority,status) VALUES('${W}','PRI-1','CT-204','SITE-104','Priority journey case','Synthetic.','document_workflow','medium','open')`);
    const job = (await call('/cases/PRI-1/investigate', {})).body; let done = null;
    for (let k = 0; k < 120 && !done; k++) { const st = (await call('/jobs/' + job.id)).body; if (st.status === 'failed') throw new Error(st.error); if (st.status === 'completed') done = st; else await page.waitForTimeout(1000); }
    const P = '/cases/PRI-1/journey';
    assert.equal((await call(P + '/subject', { id: crypto.randomUUID(), expected_rev: 0, document_system: 'mock-upload-portal', document_ref: 'DOC-5001', document_version: '2', destination_system: 'mock-binder-hub', binder_ref: 'BND-77' })).status, 200);
    const imp = async (shape, ref, h, rows, complete = true) => { const e = (await call(P + `/example?shape=${shape}`)).body; e.export.export_ref = ref; e.export.observed_at = ago(h).toISOString(); e.export.coverage.complete = complete; e.export.rows = rows; const r = await call('/operations/journey-import', { export: e.export, mapping: e.mapping }); assert.equal(r.status, 201, JSON.stringify(r.body)); };
    await imp('portal', 'P1', 6, [{ event: 'RECEIPT', receipt_no: 'RCPT-1', doc_id: 'DOC-5001', doc_rev: '2', state: 'RECEIVED', at: ago(6).toISOString() }]);
    await imp('hub', 'H1', 5, [{ kind: 'sync_job', job: { id: 'JOB-7001' }, item: {}, outcome: 'failed', when: ago(5).toISOString(), target: 'BND-77' }], false);
    assert.equal((await call(P + '/outcomes', { id: crypto.randomUUID(), key: crypto.randomUUID(), expected_rev: 0, description: 'The same document/version is filed and visible in the intended binder.', requirements: [{ stage: 'destination_filing', status: 'completed' }, { stage: 'binder_visibility', status: 'visible' }], required: true, remediation_at: ago(3).toISOString() })).status, 201);
    assert.equal((await call('/contacts', { id: crypto.randomUUID(), name: 'Binder hub support', category: 'synchronization', primary_contact: 'hub@sample.invalid', study_id: 'CT-204', site_id: 'SITE-104' })).status, 200);

    await page.goto(base + '/workspace/cases/PRI-1'); await page.waitForLoadState('networkidle');
    const j = page.locator('section[aria-label="Document journey"]'); await j.waitFor();
    await j.getByText(/Collection plan · suggested request order/).click();
    const prio = j.locator('.prio'); await prio.getByText(/Suggested request order/).first().waitFor();
    await prio.getByText(/not an optimal or predicted ranking/).waitFor();
    await prio.locator('.prio-list').first().locator('.prio-item').first().getByText(/could help assess \d+ checks?/).waitFor();
    assert(!(await prio.innerText()).toLowerCase().includes('will resolve'));
    step('suggested order shows what each request could help assess (never "will resolve"), with the rule labelled as not an optimal ranking');

    // effort + prerequisite make a request blocked and move it after ready ones
    const items = () => prio.locator('.prio-list').first().locator('.prio-item');
    const firstTitle = await items().first().locator('.prio-head b').innerText();
    await prio.getByText('Mappings, effort and prerequisites for each request').click();
    const edit = prio.locator('details.prio-edit > summary', { hasText: 'Mappings, effort and prerequisites · ' + firstTitle }).locator('..');
    await edit.locator(':scope > summary').click();
    await edit.getByLabel(/Effort \(your estimate/).selectOption('low'); await edit.getByLabel('Short explanation').fill('One lookup.');
    const other = edit.locator('fieldset', { hasText: 'Prerequisites' }).locator('label.check', { hasText: 'Request:' }).first(); const otherTitle = (await other.innerText()).replace('Request: ', '').trim();
    await other.locator('input').check();
    await edit.getByRole('button', { name: 'Save effort and prerequisites' }).click();
    await prio.locator('.prio-item.s-blocked').first().waitFor();
    assert.equal(await items().last().locator('.prio-head b').innerText(), firstTitle, 'blocked request sorts last');
    await prio.getByText(/Prerequisite not met:/).first().waitFor();
    step('effort and a prerequisite are saved; the blocked request moves after the ready ones and says why');

    // save, keyboard override, reason preserved across collapse/expand
    await prio.getByRole('button', { name: 'Save this suggested order' }).click(); await prio.getByText(/Saved as version 1/).waitFor();
    const rev = prio.locator('details.prio-edit', { has: page.locator('summary', { hasText: 'Reviewer order (override' }) }); await rev.locator(':scope > summary').click();
    const down = rev.getByRole('button', { name: /^Move down:/ }).first(); await down.focus(); await page.keyboard.press('Enter');
    await rev.getByLabel('Reason for your order').fill('The hub contact is available today.');
    await rev.locator(':scope > summary').click(); await rev.locator(':scope > summary').click();
    assert.equal(await rev.getByLabel('Reason for your order').inputValue(), 'The hub contact is available today.'); step('keyboard reorder works and the entered reason survives collapse/expand');
    await rev.getByRole('button', { name: 'Save reviewer order' }).click(); await prio.getByText(/Reviewer order in effect/).waitFor(); await prio.getByText(/Reviewer order #1; calculated #/).first().waitFor();
    step('reviewer override saved with its reason; calculated rank stays visible beside it');

    // new evidence makes it stale; refresh creates a new version and keeps the override in history
    await imp('hub', 'H2', 2, [{ kind: 'sync_job', job: { id: 'JOB-7002' }, item: {}, outcome: 'ok', when: ago(2).toISOString(), target: 'BND-77' }]);
    await page.reload(); await page.waitForLoadState('networkidle'); await j.waitFor(); await j.getByText(/Collection plan · suggested request order/).click();
    await prio.getByText(/saved order is stale/).waitFor();
    await prio.getByRole('button', { name: 'Refresh saved order' }).click(); await prio.getByText(/Saved as version 3/).waitFor();
    await prio.getByText(/No reviewer override/).waitFor();
    await prio.getByText(/Saved versions · 3/).click(); await prio.getByText(/reviewer override: The hub contact is available today\./).waitFor();
    step('new evidence marks the saved order stale; refresh adds a version without carrying the override; history keeps it');

    // draft from a suggestion through the existing workflow (editable, contact, unsent)
    const cand = items().first(); await cand.getByText(/Plan evidence request/).click();
    const q = cand.getByLabel(/Question \(editable/); await q.fill((await q.inputValue()) + ' Include the export reference.');
    await cand.getByLabel(/Responsible contact/).selectOption({ index: 1 });
    await cand.getByRole('button', { name: 'Save draft request' }).click();
    await prio.getByText(/draft request \(unsent\)/).first().waitFor(); await prio.getByText(/draft exists/).first().waitFor(); await prio.getByText('Open existing draft').first().waitFor();
    const ev = sql(`SELECT count(*) FROM case_events WHERE workspace_id='${W}' AND case_id='PRI-1' AND event_type='journey_collection_drafted' AND payload->>'from_suggested_order'='true'`); assert.equal(ev, '1');
    step('selecting a candidate opens the existing editable draft form; the draft is unsent, shows "Open existing draft", and the suggestion origin is recorded');

    // screenshots + layout
    await noOverflow('desktop');
    await prio.scrollIntoViewIfNeeded(); await prio.screenshot({ path: shots + '/priority-1440.png' });
    await page.setViewportSize({ width: 390, height: 844 }); await page.waitForTimeout(300); await noOverflow('390');
    await prio.screenshot({ path: shots + '/priority-390.png' });
    await page.setViewportSize({ width: 1440, height: 900 });
    assert.deepEqual(errors, [], errors.join('; '));
    console.log('PASS: suggested request order browser check');
  } finally { if (W) sql(`DELETE FROM workspaces WHERE id='${W}'`); await browser.close(); }
})().catch(e => { console.error('FAIL:', e); process.exit(1); });
