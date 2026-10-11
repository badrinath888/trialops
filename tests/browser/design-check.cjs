// UI-only fixtures exercise states without changing existing records or security paths.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const base = process.env.TEST_WEB_URL || 'http://localhost:3002';
const out = process.env.TEST_SCREENSHOT_DIR || path.resolve(__dirname, '../../artifacts/ui-refinement/states');
fs.mkdirSync(out, { recursive: true });
(async () => {
 const browser = await chromium.launch({headless:true, ...(process.env.CHROMIUM_PATH ? {executablePath:process.env.CHROMIUM_PATH} : {})});
 const page = await browser.newPage({viewport:{width:1440,height:900}}), report = {states:[],errors:[],fixtures:'UI response fixtures; no saved-record changes'};
 page.on('pageerror', e => report.errors.push(e.message));
 const go = async route => {await page.goto(base+route);await page.waitForLoadState('networkidle');};
 const shot = async name => {assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),name+' overflow');await page.screenshot({path:path.join(out,name+'.png'),fullPage:true,animations:'disabled'});report.states.push(name);};
 const stub = async (url,body) => page.route('**/api/'+url, r => r.fulfill({json:body}));
 try {
  for(const width of [1440,390]) {
   await page.setViewportSize({width,height:900});
   await go('/account-access');await page.getByRole('heading',{name:'Recover account access',exact:true}).waitFor();await shot('recovery-'+width);
   await go('/account-access#reset:ui-fixture');await page.getByRole('heading',{name:'Reset password',exact:true}).waitFor();assert(!page.url().includes('#'));await shot('reset-'+width);
   await go('/account-access#verify:ui-fixture');await page.getByRole('heading',{name:'Verify email',exact:true}).waitFor();await shot('verify-'+width);
   await go('/respond');await page.getByRole('alert').filter({hasText:'Response link unavailable'}).waitFor();await shot('response-unavailable-'+width);
  }
  await page.setViewportSize({width:1440,height:900});await go('/');await page.getByRole('button',{name:'Explore a sample case',exact:true}).first().click();await page.waitForURL('**/workspace');await page.waitForLoadState('networkidle');
  const me=await (await page.request.get(base+'/api/auth/me')).json();report.sample={workspace:me.workspace_id,user:me.user_id||me.id};
  await stub('my-work',{act:[],waiting:[],team_visibility:true});
  await stub('runs?*',{items:[],total:0});
  await stub('knowledge',[]);await stub('operations',[]);await stub('feedback',[]);
  for(const width of [1440,390]) {
   await page.setViewportSize({width,height:900});
   await go('/workspace/cases');await page.getByLabel('Search cases').fill('no-matching-case-ui-fixture');await page.getByRole('heading',{name:'No matching cases',exact:true}).waitFor();await shot('empty-cases-'+width);
   for(const [name,route] of [['queue','/workspace'],['history','/workspace/history'],['knowledge','/workspace/knowledge'],['operations','/workspace/operations'],['feedback','/workspace/feedback'],['roi','/workspace/roi']]) {await go(route);await shot('empty-'+name+'-'+width);}
  }
  await page.unroute('**/api/my-work');
  const rows=Array.from({length:7},(_,i)=>({title:'Synthetic long case title '+('receipt verification and site reconciliation ').repeat(6)+i,reason:'Waiting for a saved receipt and a current observation.',due_at:'2026-10-11T12:00:00Z',href:'/workspace/cases/CASE-4',action:'requests',label:'Review request'}));
  await stub('my-work',{act:rows,waiting:[],team_visibility:true});
  for(const width of [1440,390]) {
   await page.setViewportSize({width,height:900});await go('/workspace');assert.equal(await page.locator('.my-work .work-item:visible').count(),5);await page.getByText('Show 2 more items',{exact:true}).click();assert.equal(await page.locator('.my-work .work-item:visible').count(),7);await shot('long-titles-expanded-'+width);
  }
  await page.unroute('**/api/my-work');
  await page.route('**/api/my-work',async r=>{await new Promise(resolve=>setTimeout(resolve,1800));await r.fulfill({json:{act:[],waiting:[],team_visibility:false}})});
  await page.goto(base+'/workspace');await page.getByRole('status').filter({hasText:'Loading your work'}).waitFor();await shot('queue-loading');await page.waitForLoadState('networkidle');await page.unroute('**/api/my-work');
  await page.route('**/api/my-work',r=>r.fulfill({status:503,json:{detail:'Work queue is temporarily unavailable. Retry after reconnecting.'}}));
  await go('/workspace');await page.getByRole('alert').filter({hasText:'Work queue is temporarily unavailable'}).waitFor();await shot('queue-error');await page.unroute('**/api/my-work');
  await page.unroute('**/api/knowledge');await go('/workspace/knowledge');await page.getByRole('button',{name:/Uploaded training certificate.*v1/}).click();await page.getByRole('button',{name:'Edit procedure',exact:true}).click();const text=page.getByLabel('Procedure text',{exact:true});await text.fill('Synthetic unsaved draft retained until explicitly discarded.');
  page.once('dialog',d=>d.dismiss());await page.getByRole('button',{name:'Close procedure',exact:true}).click();assert.equal(await text.inputValue(),'Synthetic unsaved draft retained until explicitly discarded.');await shot('unsaved-form-retained');page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'Close procedure',exact:true}).click();
  await page.emulateMedia({reducedMotion:'reduce'});await go('/workspace/cases');const preview=page.getByRole('button',{name:'Preview CASE-4',exact:true});await preview.click();const dialog=page.getByRole('dialog');await dialog.waitFor();await dialog.getByRole('link',{name:'Open full case →'}).waitFor();await dialog.getByRole('button',{name:'Close preview'}).press('Shift+Tab');assert(await dialog.getByRole('link',{name:'Open full case →'}).evaluate(e=>e===document.activeElement));await page.keyboard.press('Escape');assert(await preview.evaluate(e=>e===document.activeElement));
  assert.equal(await preview.evaluate(e=>getComputedStyle(e).transitionDuration),'0s');await preview.focus();assert(await preview.evaluate(e=>getComputedStyle(e).outlineStyle!=='none'));await shot('keyboard-focus-reduced-motion');
  await stub('cases/CASE-4/next-step',{version:'ui-fixture',primary:{action:'continuity',label:'Review handover',reason:'Review the current handover.'},actions:[{action:'continuity',label:'Review handover'}],blockers:[]});
  await stub('cases/CASE-4/next-step/open',{opened:true});await go('/workspace/cases/CASE-4');await page.evaluate(()=>{window.uiScrollOptions=null;const original=Element.prototype.scrollIntoView;Element.prototype.scrollIntoView=function(options){window.uiScrollOptions=options;return original.call(this,options)}});await page.getByRole('button',{name:'Next step: Review handover',exact:true}).click();await page.locator('#case-continuity[open]').waitFor();assert.equal(await page.evaluate(()=>window.uiScrollOptions?.behavior),'auto');await shot('guided-action-reduced-motion');
  assert.deepEqual(report.errors,[]);
  console.log('PASS: '+report.states.length+' empty/public/long-title/loading/error/unsaved/focus/reduced-motion states.');
 } finally {fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
