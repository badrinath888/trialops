// Reviewed-response attestation form and snapshot-only confirmed links in the UI (TEST stack 3002; fresh sample workspace, deleted at the end).
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const base = process.env.TEST_WEB_URL || 'http://localhost:3002';
const DB = process.env.TEST_DB_CONTAINER || 'trialops-release-test-db-1';
const API = process.env.TEST_API_CONTAINER || 'trialops-release-test-api-1';
const sql = q => execFileSync('docker', ['exec', '-i', DB, 'psql', '-U', 'trialops', '-d', 'trialops', '-At', '-c', q]).toString().trim();
const __memo = {}; const ago = h => (__memo[h] ||= new Date(Date.now() - h * 3600e3)); // stable per hours so an export and its rows share one instant
(async () => {
  const options = { headless: true }; if (process.env.CHROMIUM_PATH) options.executablePath = process.env.CHROMIUM_PATH;
  const browser = await chromium.launch(options), errors = [];
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  page.on('pageerror', e => errors.push(e.message));
  let W = null; const step = s => console.log('OK:', s);
  const call = (path, body) => page.evaluate(async ([p, b]) => { const r = await fetch('/api' + p, { method: b ? 'POST' : 'GET', headers: { 'Content-Type': 'application/json' }, body: b ? JSON.stringify(b) : undefined }); return { status: r.status, body: await r.json().catch(() => ({})) }; }, [path, body]);
  try {
    await page.goto(base + '/'); await page.getByRole('button', { name: 'Explore a sample case', exact: true }).first().click(); await page.waitForURL('**/workspace'); await page.waitForLoadState('networkidle');
    const me = await (await page.request.get(base + '/api/auth/me')).json(); W = me.workspace_id;
    const job = (await call('/cases/CASE-4/investigate', {})).body; let run = null;
    for (let k = 0; k < 120 && !run; k++) { const st = (await call('/jobs/' + job.id)).body; if (st.status === 'completed') run = st.result_id; else if (st.status === 'failed') throw new Error(st.error); else await page.waitForTimeout(1000); }
        const reqId = crypto.randomUUID(), linkId = crypto.randomUUID(), respId = crypto.randomUUID();
    sql(`INSERT INTO information_requests(workspace_id,id,case_id,run_id,title,items,status) VALUES('${W}','${reqId}','CASE-4','${run}','Ask hub','["Which job?"]','requested')`);
    sql(`INSERT INTO external_response_links(workspace_id,id,case_id,request_id,token_hash,question,expires_at) VALUES('${W}','${linkId}','CASE-4','${reqId}','${crypto.randomUUID()}','{}',now()+interval '1 day')`);
    sql(`INSERT INTO external_responses(workspace_id,id,case_id,request_id,link_id,submission_id,text,status,reviewer_name,reviewed_at,submitted_at) VALUES('${W}','${respId}','CASE-4','${reqId}','${linkId}','${crypto.randomUUID()}','The hub reports the filing completed for DOC-5001 in BND-77.','accepted','Sample visitor',now(),now()-interval '30 minutes')`);
    assert.equal((await call('/cases/CASE-4/journey/subject', { id: crypto.randomUUID(), expected_rev: 0, document_system: 'mock-upload-portal', document_ref: 'DOC-5001', document_version: '2', destination_system: 'mock-binder-hub', binder_ref: 'BND-77' })).status, 200);
    const hub = (await call('/cases/CASE-4/journey/example?shape=hub')).body; hub.export.export_ref = 'H-P'; const t2 = ago(2).toISOString(); hub.export.observed_at = t2;
    hub.export.rows = [{ kind: 'sync_job', job: { id: 'JOB-7001' }, item: {}, outcome: 'failed', when: t2, target: 'BND-77' }];
    { const r = await call('/operations/journey-import', { export: hub.export, mapping: hub.mapping }); assert.equal(r.status, 201, JSON.stringify(r.body)); }
    await page.goto(base + '/workspace/cases/CASE-4'); await page.waitForLoadState('networkidle');
    const j = page.locator('section[aria-label="Document journey"]'); await j.waitFor();
    const filing = j.locator('details.journey-stage', { hasText: 'Destination filing' });
    await filing.locator(':scope > summary').click();
    await filing.getByText('Record a reviewed response as an attested observation').click();
    const form = filing.locator('details.journey-inline', { hasText: 'Record a reviewed response' }); const resp = form.getByLabel('Reviewed response'); const opts = await resp.locator('option').allTextContents();
    assert(opts.some(o => /reviewed/.test(o)) && !opts.some(o => /Unreviewed/.test(o)), JSON.stringify(opts)); step('only reviewed responses are offered');
    await resp.selectOption({ index: 1 });
    await form.getByLabel('Source system').fill('mock-binder-hub'); await form.getByLabel('Record reference').fill('FILE-A'); await form.getByLabel('Document ID').fill('DOC-5001'); await form.getByLabel('Version').fill('2'); await form.getByLabel('Binder ID').fill('BND-77');
    await form.getByLabel('Reported status').selectOption('completed');
    await form.getByLabel(/Observed at/).fill(new Date(ago(1).getTime() - ago(1).getTimezoneOffset() * 60000).toISOString().slice(0, 16));
    await form.getByLabel(/Why these fields/).fill('Reviewer transcribed the identifiers the hub reported.');
    await form.getByRole('button', { name: 'Save attested observation' }).click();
    await filing.getByText(/Attested by a reviewed response \(not verification\)/).waitFor();
    await filing.getByText(/not verified by a system record/).waitFor();
    await j.getByText(/Destination filing: unknown/).waitFor(); step('attested observation saved with provenance; the stage stays unknown');
    await j.getByText(/Existing confirmed links · saved snapshots only/).count().then(c => assert.equal(c, 0));
    assert.deepEqual(errors, [], errors.join('; '));
    console.log('PASS: journey provenance browser check');
  } finally { if (W) sql(`DELETE FROM workspaces WHERE id='${W}'`); await browser.close(); }
})().catch(e => { console.error('FAIL:', e); process.exit(1); });
