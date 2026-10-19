// Freshness and remediation-date semantics through the UI on the TEST stack (3002). Fresh expiring sample workspace; policy changes are restored and the workspace deleted.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const base = require('./target.cjs')();
const DB = process.env.TEST_DB_CONTAINER || 'trialops-release-test-db-1';
const sql = q => execFileSync('docker', ['exec', '-i', DB, 'psql', '-U', 'trialops', '-d', 'trialops', '-At', '-c', q]).toString().trim();
const __memo = {}; const ago = h => (__memo[h] ||= new Date(Date.now() - h * 3600e3)); // stable per hours so an export and its rows share one instant
(async () => {
  const options = { headless: true }; if (process.env.CHROMIUM_PATH) options.executablePath = process.env.CHROMIUM_PATH;
  const browser = await chromium.launch(options), errors = [];
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  page.on('pageerror', e => errors.push(e.message));
  let W = null; const step = s => console.log('OK:', s);
  const call = (path, body) => page.evaluate(async ([p, b]) => { const r = await fetch('/api' + p, { method: b ? 'POST' : 'GET', headers: { 'Content-Type': 'application/json' }, body: b ? JSON.stringify(b) : undefined }); return { status: r.status, body: await r.json().catch(() => ({})) }; }, [path, body]);
  const policy = async hours => { const cur = (await call('/policies')).body; const r = await call('/policies', { expected_version: cur.version, freshness_hours: hours, reminder_lead_hours: cur.reminder_lead_hours, reminder_frequency_minutes: cur.reminder_frequency_minutes, visit_checklist: cur.visit_checklist }); assert.equal(r.status, 200, JSON.stringify(r.body)); };
  try {
    await page.goto(base + '/'); await page.getByRole('button', { name: 'Explore a sample case', exact: true }).first().click(); await page.waitForURL('**/workspace'); await page.waitForLoadState('networkidle');
    W = (await (await page.request.get(base + '/api/auth/me')).json()).workspace_id;
    assert.equal((await call('/policies')).body.freshness_hours, null); // starting state, restored at the end
    sql(`INSERT INTO cases(workspace_id,id,study_id,site_id,title,description,category,priority,status) VALUES('${W}','JRN-F','CT-204','SITE-104','Freshness case','Synthetic.','document_workflow','medium','open')`);
    const P = '/cases/JRN-F/journey';
    assert.equal((await call(P + '/subject', { id: crypto.randomUUID(), expected_rev: 0, document_system: 'mock-upload-portal', document_ref: 'DOC-5001', document_version: '2', destination_system: 'mock-binder-hub', binder_ref: 'BND-77' })).status, 200);
    const hub = (await call(P + '/example?shape=hub')).body; hub.export.export_ref = 'H-F'; hub.export.observed_at = ago(5).toISOString();
    hub.export.rows = [{ kind: 'filing', job: { id: 'FILE-F' }, item: { upstream: 'DOC-5001', rev: '2' }, outcome: 'filed', when: ago(5).toISOString(), target: 'BND-77' }, { kind: 'visibility', job: { id: 'VIS-F' }, item: { upstream: 'DOC-5001', rev: '2' }, outcome: 'shown', when: ago(5).toISOString(), target: 'BND-77' }];
    assert.equal((await call('/operations/journey-import', { export: hub.export, mapping: hub.mapping })).status, 201);
    assert.equal((await call(P + '/links', { id: crypto.randomUUID(), kind: 'document', from_system: 'mock-binder-hub', from_ref: 'DOC-5001', rationale: 'Hub admin record names the portal document.', evidence: 'Hub admin record 44' })).status, 201);
    const key = crypto.randomUUID(); let rev = 0;
    const outcome = async remediationHoursAgo => { const r = await call(P + '/outcomes', { id: crypto.randomUUID(), key, expected_rev: rev, description: 'The same document/version is filed and visible in the intended binder.', requirements: [{ stage: 'destination_filing', status: 'completed' }, { stage: 'binder_visibility', status: 'visible' }], required: true, remediation_at: ago(remediationHoursAgo).toISOString() }); assert.equal(r.status, 201, JSON.stringify(r.body)); rev++; };
    await outcome(8);
    await page.goto(base + '/workspace/cases/JRN-F'); await page.waitForLoadState('networkidle');
    const j = page.locator('section[aria-label="Document journey"]'); await j.waitFor();
    const verify = async (expected, reason) => {
      await page.reload(); await page.waitForLoadState('networkidle'); await j.waitFor();
      await j.getByText(/Expected outcomes and verification/).click();
      await j.getByLabel('Rationale for this verification').fill('Verification run in the freshness check.'); await j.getByRole('button', { name: 'Record verification' }).click();
      await j.getByText(new RegExp(expected + ' — recorded')).waitFor();
      if (reason) await j.getByText(reason).first().waitFor();
    };
    await verify('Verified'); step('evidence after remediation verifies when no freshness policy is configured (no invented threshold)');
    await policy(2); await verify('Insufficient evidence', /older than the workspace freshness policy \(2 hours\)/);
    await j.locator('details.journey-stage', { hasText: 'Destination filing' }).locator(':scope > summary').click(); await j.locator('details.journey-stage', { hasText: 'Destination filing' }).getByText(/older than the workspace freshness policy/).first().waitFor(); step('configured 2-hour policy: 5-hour-old evidence cannot verify and is labelled stale');
    await policy(12); await verify('Verified'); step('12-hour policy: the same evidence is within limit and verifies (positive control)');
    await policy(null); await outcome(1); await verify('Insufficient evidence', /earlier observation\(s\) do not count/); step('evidence that predates the remediation point cannot verify');
    assert.equal((await call('/policies')).body.freshness_hours, null); step('test policy restored to its starting state');
    assert.equal(sql(`SELECT status FROM cases WHERE workspace_id='${W}' AND id='JRN-F'`), 'open');
    assert.deepEqual(errors, [], errors.join('; '));
    console.log('PASS: journey freshness/remediation browser check');
  } finally { if (W) sql(`DELETE FROM workspaces WHERE id='${W}'`); await browser.close(); }
})().catch(e => { console.error('FAIL:', e); process.exit(1); });
