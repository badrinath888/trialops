// Populated desktop + 390px journey for recurrence/prevention, bulk actions, readiness, procedure impact and feedback queue.
// Uses a fresh expiring sample workspace on the TEST stack (default http://localhost:3002); rows are added to that workspace only and it is deleted at the end.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const base = process.env.TEST_WEB_URL || 'http://localhost:3002';
const DB = process.env.TEST_DB_CONTAINER || 'trialops-release-test-db-1';
const sql = q => execFileSync('docker', ['exec', '-i', DB, 'psql', '-U', 'trialops', '-d', 'trialops', '-At', '-c', q]).toString().trim();
(async () => {
 const options = { headless: true }; if (process.env.CHROMIUM_PATH) options.executablePath = process.env.CHROMIUM_PATH;
 const browser = await chromium.launch(options), errors = [];
 const context = await browser.newContext({ viewport: { width: 1440, height: 900 } }), page = await context.newPage();
 page.on('pageerror', e => errors.push(e.message));
 let W = null; const step = s => console.log('OK:', s);
 try {
  await page.goto(base + '/'); await page.getByRole('button', { name: 'Explore a sample case', exact: true }).first().click(); await page.waitForURL('**/workspace'); await page.waitForLoadState('networkidle');
  W = (await (await page.request.get(base + '/api/auth/me')).json()).workspace_id;
  const me = await (await page.request.get(base + '/api/auth/me')).json();
  for (const i of [1, 2, 3]) sql(`INSERT INTO cases(workspace_id,id,study_id,site_id,title,description,category,priority,created_at) VALUES('${W}','REC-${i}','CT-204','SITE-104','Receipt gap REC-${i}','Synthetic recurring upload receipt gap for browser testing.','document_workflow','medium',now()-interval '${i} days')`);
  const art = 'KB-IMPACT', t1 = '# Escalation\\nEscalate after 15 minutes.\\n\\n# Receipts\\nCheck the upload receipt.', t2 = '# Escalation\\nEscalate after 30 minutes.\\n\\n# Receipts\\nCheck the upload receipt.\\n\\n# Audit\\nRecord the reviewer.';
  sql(`INSERT INTO knowledge(workspace_id,id,title,content,category,version) VALUES('${W}','${art}','Impact procedure',E'${t2}','document_workflow',2)`);
  sql(`INSERT INTO procedure_versions(workspace_id,article_id,version,title,content,category) VALUES('${W}','${art}',1,'Impact procedure',E'${t1}','document_workflow'),('${W}','${art}',2,'Impact procedure',E'${t2}','document_workflow')`);
  const noOverflow = async name => assert((await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)) <= 1, name + ' overflows horizontally');

  // 1. recurrence + prevention plan
  await page.goto(base + '/workspace/cases/REC-1'); await page.waitForLoadState('networkidle');
  const rec = page.locator('section[aria-label="Recurrence and prevention"]'); await rec.waitFor();
  await rec.getByText('Confirm a recurrence group').click();
  await rec.getByLabel(/REC-2/).check(); await rec.getByLabel(/REC-3/).check();
  await rec.getByLabel('Group name').fill('Receipt gaps at SITE-104');
  await rec.getByLabel(/What pattern did you observe/).fill('Three uploads lacked receipts after the nightly sync window.');
  await rec.getByRole('button', { name: 'Confirm group membership' }).click();
  await rec.getByText(/Receipt gaps at SITE-104 · 3 cases/).waitFor(); step('recurrence group confirmed by reviewer with explained pattern');
  await rec.getByText(/Receipt gaps at SITE-104 · 3 cases/).click();
  await rec.getByText(/does not establish a shared root cause|do not establish a shared root cause/).first().waitFor();
  await rec.getByLabel('New plan title').fill('Receipt prevention'); await rec.getByRole('button', { name: 'Create draft plan' }).click();
  await rec.getByText(/Receipt prevention · draft/).waitFor(); await rec.getByText(/Receipt prevention · draft/).click();
  await rec.getByRole('button', { name: 'Add action' }).click();
  const act = rec.locator('fieldset.improve-action').first();
  await act.getByLabel('What will be done').fill('Add nightly receipt reconciliation');
  await act.getByLabel('Owner').selectOption({ index: 1 }); await act.getByLabel('Deadline').fill('2026-12-01'); await act.getByLabel('Supporting case').selectOption('REC-1');
  await rec.getByRole('button', { name: 'Activate plan' }).click(); await rec.getByText(/Receipt prevention · active/).waitFor(); step('prevention plan with owner, deadline, evidence activated');
  await rec.getByText('Subsequent matching cases').scrollIntoViewIfNeeded();
  await rec.getByLabel('Window label').fill('Baseline'); await rec.getByLabel('Start').fill('2026-09-01'); await rec.getByLabel('End (exclusive)').fill('2026-10-01');
  await rec.getByRole('button', { name: 'Record window' }).click(); await rec.getByText(/Baseline \(baseline\)/).waitFor();
  await rec.getByText(/No comparison made/).waitFor(); await noOverflow('case recurrence'); step('windows recorded; comparison refused without follow-up/exposure; no causal claim');

  // 2. bulk actions
  await page.goto(base + '/workspace/cases'); await page.waitForLoadState('networkidle');
  await page.getByLabel('Search cases').fill('Receipt gap'); await page.getByText(/Receipt gap REC-1/).waitFor();
  await page.getByLabel('Select REC-2').focus(); await page.keyboard.press('Space'); await page.getByLabel('Select REC-3').check();
  const bulk = page.locator('section[aria-label="Bulk case actions"]'); await bulk.getByText('2 selected').waitFor();
  await bulk.getByLabel('Change owner').check(); await bulk.locator('select').first().selectOption({ index: 1 });
  await bulk.getByRole('button', { name: 'Preview changes' }).click(); await bulk.getByText('Will change').first().waitFor();
  await bulk.getByRole('button', { name: /Apply to 2 cases/ }).click(); await bulk.getByText(/2 updated/).waitFor(); step('bulk owner change: preview then confirm; per-case results');
  assert.equal(sql(`SELECT count(*) FROM cases WHERE workspace_id='${W}' AND id IN ('REC-2','REC-3') AND owner_id IS NOT NULL AND status='open'`), '2');

  // 3. readiness
  await page.goto(base + '/workspace/operations'); await page.waitForLoadState('networkidle');
  const rd = page.locator('section[aria-label="Document readiness tracker"]'); await rd.waitFor();
  await rd.getByRole('button', { name: 'Define required document' }).click(); await rd.getByLabel('Name').fill('Delegation log'); await rd.getByRole('button', { name: 'Save requirement' }).click();
  await rd.getByText('Missing').first().waitFor(); await rd.getByRole('button', { name: 'Record' }).first().click();
  await rd.getByLabel('Document identity').fill('DEL-LOG-001'); await rd.getByLabel('Document version').fill('3'); await rd.getByLabel(/Date you observed/).fill('2026-10-01'); await rd.getByLabel(/Where it is filed/).fill('TMF 4.2.1');
  await rd.getByRole('button', { name: 'Save record' }).click(); await rd.getByText('Not yet reviewed.').waitFor();
  await rd.getByRole('button', { name: 'Record' }).first().click(); await rd.getByRole('button', { name: 'Mark reviewed' }).click(); await rd.getByText(/Reviewed as recorded for 2026-10-01/).waitFor();
  assert.equal(sql(`SELECT expiry_date IS NULL FROM readiness_records WHERE workspace_id='${W}'`), 't'); step('readiness: missing -> awaiting review -> reviewed; no expiry inferred');
  await rd.getByRole('button', { name: 'Edit requirement' }).first().click(); await rd.getByLabel('Name').fill('Delegation log (rev 2)'); await rd.getByRole('button', { name: 'Save requirement' }).click();
  await rd.getByText(/requirement changed after this record was reviewed/).waitFor(); await noOverflow('operations readiness'); step('changing the requirement invalidates the earlier review');

  // 4. procedure impact
  await page.goto(base + '/workspace/knowledge'); await page.waitForLoadState('networkidle');
  const imp = page.locator('section[aria-label="Procedure change impact review"]'); await imp.waitFor();
  await imp.getByLabel('Procedure').selectOption(art); await imp.getByText(/Changed passages \(2\)/).waitFor();
  await imp.getByText(/not AI output/).first().waitFor();
  await imp.getByText('Escalate after 30 minutes.').waitFor();
  await imp.getByLabel(/Why \(at least 10/).fill('Escalation threshold changed from 15 to 30 minutes.'); await imp.getByRole('button', { name: 'Record review' }).click();
  await imp.getByText(/Reviewed:/).waitFor(); await noOverflow('knowledge impact'); step('procedure impact: exact changed passages, human reassessment decision recorded, nothing rewritten');

  // 5. feedback
  await page.goto(base + '/workspace/feedback'); await page.waitForLoadState('networkidle');
  await page.getByLabel('Your feedback').fill('The recurrence panel is hard to find on narrow screens.'); await page.getByRole('button', { name: 'Submit feedback' }).click();
  const q = page.locator('section[aria-label="Feedback queue"]'); await q.getByText(/recurrence panel is hard to find/).waitFor();
  await q.getByRole('button', { name: 'Triage' }).first().click();
  const tri = q.locator('form[aria-label="Triage feedback"]'); await tri.getByLabel('State').selectOption('planned'); await tri.getByLabel(/Safe status note/).fill('Planned for the next release.'); await tri.getByLabel(/Internal note/).fill('INTERNAL: do not show');
  await tri.getByRole('button', { name: 'Save triage' }).click();
  await page.reload(); await page.waitForLoadState('networkidle');
  const mine = page.locator('section[aria-label="Your feedback status"]'); await mine.getByText('Planned for the next release.').waitFor();
  assert(!(await mine.innerText()).includes('INTERNAL')); step('feedback triaged; submitter sees only status and the safe note');

  // 6. narrow layout
  await page.setViewportSize({ width: 390, height: 844 });
  for (const [route, sel] of [['/workspace/cases/REC-1', 'section[aria-label="Recurrence and prevention"]'], ['/workspace/operations', 'section[aria-label="Document readiness tracker"]'], ['/workspace/knowledge', 'section[aria-label="Procedure change impact review"]'], ['/workspace/feedback', 'section[aria-label="Feedback queue"]'], ['/workspace/cases', 'section[aria-label="Bulk case actions"], .case-toolbar']]) {
   await page.goto(base + route); await page.waitForLoadState('networkidle'); await page.locator(sel).first().waitFor(); await noOverflow('390px ' + route);
  }
  step('390px layouts have no page-level horizontal overflow');
  assert.deepEqual(errors, [], 'page errors: ' + errors.join('; '));
  console.log('PASS: improvement workflows journey (desktop + 390px), zero page errors');
 } finally {
  if (W) sql(`DELETE FROM workspaces WHERE id='${W}'; DELETE FROM users WHERE guest AND NOT EXISTS(SELECT 1 FROM memberships m WHERE m.user_id=users.id)`);
  await browser.close();
 }
})().catch(e => { console.error('FAIL:', e.message.split('\n').slice(0, 6).join('\n')); process.exit(1); });
