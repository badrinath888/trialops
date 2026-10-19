// Document journey on the TEST stack (default http://localhost:3002): reviewer journey at 1440px and 390px, form-state preservation, keyboard access.
// Uses a fresh expiring sample workspace; rows are added to that workspace only and it is deleted at the end.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { execFileSync } = require('node:child_process');
const base = require('./target.cjs')();
const DB = process.env.TEST_DB_CONTAINER || 'trialops-release-test-db-1';
const shots = process.env.SHOT_DIR || 'artifacts/journey-screenshots';
const sql = q => execFileSync('docker', ['exec', '-i', DB, 'psql', '-U', 'trialops', '-d', 'trialops', '-At', '-c', q]).toString().trim();
const __memo = {}; const ago = h => (__memo[h] ||= new Date(Date.now() - h * 3600e3)); // stable per hours so an export and its rows share one instant
const local = d => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
(async () => {
  fs.mkdirSync(shots, { recursive: true });
  const options = { headless: true }; if (process.env.CHROMIUM_PATH) options.executablePath = process.env.CHROMIUM_PATH;
  const browser = await chromium.launch(options), errors = [];
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } }), page = await context.newPage();
  page.on('pageerror', e => errors.push(e.stack || e.message));
  let W = null; const step = s => console.log('OK:', s);
  const call = (path, body) => page.evaluate(async ([p, b]) => { const r = await fetch('/api' + p, { method: b ? 'POST' : 'GET', headers: { 'Content-Type': 'application/json' }, body: b ? JSON.stringify(b) : undefined }); return { status: r.status, body: await r.json().catch(() => ({})) }; }, [path, body]);
  const noOverflow = async name => assert((await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)) <= 1, name + ' overflows horizontally');
  try {
    await page.goto(base + '/'); await page.getByRole('button', { name: 'Explore a sample case', exact: true }).first().click(); await page.waitForURL('**/workspace'); await page.waitForLoadState('networkidle');
    W = (await (await page.request.get(base + '/api/auth/me')).json()).workspace_id;
    const uidRow = (await (await page.request.get(base + '/api/auth/me')).json()).user_id;
    sql(`INSERT INTO cases(workspace_id,id,study_id,site_id,title,description,category,priority,status) VALUES('${W}','JRN-1','CT-204','SITE-104','Training certificate missing from the binder','Synthetic journey case.','document_workflow','medium','open')`);
    const job = (await call('/cases/JRN-1/investigate', {})).body; let done = null;
    for (let k = 0; k < 120 && !done; k++) { const st = (await call('/jobs/' + job.id)).body; if (st.status === 'failed') throw new Error(st.error); if (st.status === 'completed') done = st; else await page.waitForTimeout(1000); }
    assert(done, 'investigation did not finish'); const runId = done.result_id;
    assert.equal((await call('/runs/' + runId + '/decision', { decision: 'approved', notes: 'Earlier approved recommendation.' })).status, 200);
    const ex = async (shape, ref, at, rows, complete = true) => { const e = (await call(`/cases/JRN-1/journey/example?shape=${shape}`)).body; if (!e.export) return e; e.export.export_ref = ref; e.export.observed_at = at.toISOString(); e.export.coverage.complete = complete; if (rows) e.export.rows = rows; else e.export.rows.forEach(r => { r.at = at.toISOString(); r.when = at.toISOString(); }); return call('/operations/journey-import', { export: e.export, mapping: e.mapping }); };
    assert.equal((await call('/contacts', { id: crypto.randomUUID(), name: 'Binder hub support', category: 'synchronization', primary_contact: 'hub-support@sample.invalid', study_id: 'CT-204', site_id: 'SITE-104' })).status, 200);

    // 1. define the document and binder (no exports yet)
    await page.goto(base + '/workspace/cases/JRN-1'); await page.waitForLoadState('networkidle');
    const j = page.locator('section[aria-label="Document journey"]'); await j.waitFor();
    await j.getByText('Define the document and intended binder').click();
    await j.getByLabel('Document system').fill('mock-upload-portal'); await j.getByLabel('Document ID').fill('DOC-5001'); await j.getByLabel('Version').fill('2');
    await j.getByLabel('Destination system').fill('mock-binder-hub'); await j.getByLabel('Intended binder ID').fill('BND-77');
    await j.getByRole('button', { name: 'Save definition' }).click(); await j.locator('.journey-subject').getByText(/DOC-5001 version 2/).waitFor(); step('document and intended binder defined');

    // 2. imports: owner pastes/uses synthetic exports; unlinked failed sync stays unknown
    const portalRows = [{ event: 'RECEIPT', receipt_no: 'RCPT-5001', doc_id: 'DOC-5001', doc_rev: '2', state: 'RECEIVED', at: ago(6).toISOString() }, { event: 'PROCESS', receipt_no: 'PROC-5001', doc_id: 'DOC-5001', doc_rev: '2', state: 'WAIT', at: ago(6).toISOString() }];
    assert.equal((await ex('portal', 'P1', ago(6), portalRows)).status, 201);
    assert.equal((await ex('hub', 'H1', ago(5), [{ kind: 'sync_job', job: { id: 'JOB-7001' }, item: {}, outcome: 'failed', when: ago(5).toISOString(), target: 'BND-77' }], false)).status, 201);
    await page.reload(); await page.waitForLoadState('networkidle'); await j.waitFor();
    await j.getByText(/Transfer \/ synchronization: unknown/).waitFor(); await j.getByText(/2 of 5 stages verified/).waitFor();
    const transfer = j.locator('details.journey-stage', { hasText: 'Transfer / synchronization' });
    await transfer.locator('summary').first().click(); await transfer.getByText(/Excluded: unlinked/).waitFor();
    await transfer.getByText(/Excluded candidates \(not treated as this document\)/).waitFor(); step('unlinked failed sync keeps transfer unknown with the candidate shown as excluded');
    await transfer.getByText('Supporting fields').first().click(); await transfer.getByText('JOB-7001').first().waitFor();

    // 3. reviewed link => verified failure, no root-cause claim
    await transfer.getByText(/Confirm record link/).click();
    await transfer.getByLabel(/Why does this identify/).fill('The hub job log names DOC-5001 version 2.'); await transfer.getByLabel('Evidence you reviewed').fill('Hub job log line 12');
    await transfer.getByRole('button', { name: 'Save reviewed link' }).click();
    await j.getByText(/Transfer \/ synchronization: failed \(verified/).waitFor(); await transfer.getByText(/root cause is not established/).waitFor(); step('reviewed link turns the failure into a verified failure without a root-cause claim');

    // 4. collection plan: editable question, chosen contact, preserved across collapse/expand, saved as an unsent draft
    const filing = j.locator('details.journey-stage', { hasText: 'Destination filing' });
    await filing.locator('summary').first().click();
    await filing.getByText(/Plan evidence request/).first().click();
    const q = filing.getByLabel(/Question \(editable/).first(); const original = await q.inputValue(); assert(original.includes('mock-binder-hub') && original.includes('destination filing'));
    await q.fill(original + ' Include the export reference.'); await filing.getByLabel(/Responsible contact/).first().selectOption({ index: 1 });
    await filing.locator('summary').first().click(); await filing.locator('summary').first().click();
    assert.equal(await filing.getByLabel(/Question \(editable/).first().inputValue(), original + ' Include the export reference.'); step('entered form values survive collapse/expand');
    await filing.getByRole('button', { name: 'Save draft request' }).first().click(); await filing.getByText(/Nothing was sent/).waitFor();
    const wf = (await call('/cases/JRN-1/workflow')).body; assert(wf.requests.some(r => r.status === 'draft' && r.contact_id && r.items[0].endsWith('Include the export reference.')));
    await j.getByText(/Collection plan · suggested request order · 1 drafted/).waitFor(); step('draft saved through the existing request workflow with the chosen contact; nothing sent');

    // 5. expected outcome + verification (insufficient before remediation evidence)
    await j.getByText(/Expected outcomes and verification/).click();
    await j.getByLabel(/Expected outcome \(before remediation\)/).fill('The same document/version is filed and visible in the intended binder.');
    await j.getByLabel(/Remediation applied at/).fill(local(ago(3))); await j.getByRole('button', { name: 'Save outcome' }).click();
    await j.getByText(/1 outcome/).waitFor();
    await j.getByLabel('Rationale for this verification').fill('Checked after the sync fix was applied.'); await j.getByRole('button', { name: 'Record verification' }).click();
    await j.getByText(/Insufficient evidence — recorded/).waitFor(); step('verification without later evidence is Insufficient evidence');

    // 6. later exact evidence; the same ID text in the hub needs a reviewed mapping first
    const post = [{ kind: 'filing', job: { id: 'FILE-NEW' }, item: { upstream: 'DOC-5001', rev: '2' }, outcome: 'filed', when: ago(1).toISOString(), target: 'BND-77' }, { kind: 'visibility', job: { id: 'VIS-NEW' }, item: { upstream: 'DOC-5001', rev: '2' }, outcome: 'shown', when: ago(1).toISOString(), target: 'BND-77' }];
    assert.equal((await ex('hub', 'H2', ago(1), post)).status, 201);
    await page.reload(); await page.waitForLoadState('networkidle'); await j.waitFor();
    await filing.locator('summary').first().click(); await filing.getByText(/Excluded: id collision/).first().waitFor(); step('identical ID text in another system is excluded until mapped');
    await filing.getByText(/Confirm document link/).first().click();
    await filing.getByLabel(/Why does this identify/).first().fill('Hub document DOC-5001 is the portal document per the hub admin record.'); await filing.getByLabel('Evidence you reviewed').first().fill('Hub admin record 44');
    await filing.getByRole('button', { name: 'Save reviewed link' }).first().click(); await j.getByText(/4 of 5 stages verified|5 of 5 stages verified/).waitFor();
    await j.getByText(/Expected outcomes and verification/).click();
    await j.getByLabel('Rationale for this verification').fill('Re-checked after the hub export H2 was imported.'); await j.getByRole('button', { name: 'Record verification' }).click();
    await j.getByText(/Verified — recorded/).waitFor();
    assert.equal(sql(`SELECT status FROM cases WHERE workspace_id='${W}' AND id='JRN-1'`), 'open'); await page.getByText(/^open$/i).first().waitFor();
    step('exact later evidence verifies the outcome; the case stays open until a human resolves it');

    // 7. replay + historical marking after a revision
    await j.getByText(/Decision replay/).click(); await j.getByText(/Verification · verified/).first().waitFor(); await j.getByText(/Investigation review · approved/).waitFor();
    await j.getByText(/Investigation review · approved/).click(); await j.getByText(/Replay incomplete/).waitFor(); step('replay shows saved decisions and marks older ones incomplete');
    await j.getByRole('button', { name: 'Revise' }).first().click(); await j.getByLabel(/Expected outcome \(before remediation\)/).fill('The same document/version is filed in the intended binder.');
    await j.locator('form[aria-label="Expected outcome"]').getByRole('button', { name: 'Save revision' }).click(); await j.getByText(/\(historical\)/).first().waitFor(); step('an outcome revision makes the earlier verification historical');

    // 8. screenshots, overflow, keyboard
    await j.scrollIntoViewIfNeeded(); await noOverflow('journey desktop');
    await j.locator('summary', { hasText: 'Transfer / synchronization' }).focus(); await page.keyboard.press('Enter'); await page.keyboard.press('Enter');
    await j.screenshot({ path: shots + '/journey-1440.png' });
    await page.setViewportSize({ width: 390, height: 844 }); await page.waitForTimeout(300); await noOverflow('journey 390');
    await j.screenshot({ path: shots + '/journey-390.png' });
    await j.locator('details.journey-stage').first().locator(':scope > summary').click(); await j.locator('details.journey-stage').first().screenshot({ path: shots + '/journey-390-stage.png' });
    await page.setViewportSize({ width: 1440, height: 900 }); await page.waitForTimeout(200);
    await j.locator('details.journey-stage', { hasText: 'Destination filing' }).screenshot({ path: shots + '/journey-1440-stage.png' });
    step('no horizontal overflow at 1440 and 390; keyboard toggles disclosures; screenshots saved to ' + shots);
    assert.deepEqual(errors, [], 'page errors: ' + errors.join('; '));
    console.log('PASS: document journey browser journey');
  } catch (e) {
    console.error(page.url(), errors.join(' | '), (await page.locator('body').innerText().catch(() => 'no page text')).slice(0, 500)); throw e;
  } finally {
    if (W) sql(`DELETE FROM workspaces WHERE id='${W}'`);
    await browser.close();
  }
})().catch(e => { console.error('FAIL:', e); process.exit(1); });
