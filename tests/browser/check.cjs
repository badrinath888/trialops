// Run against a test installation. Creates a temporary sample workspace (24-hour expiry).
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const base=require('./target.cjs')();
const out=process.env.TEST_SCREENSHOT_DIR||path.resolve('screenshots');fs.mkdirSync(out,{recursive:true});
const options={headless:true};
if(process.env.CHROMIUM_PATH)options.executablePath=process.env.CHROMIUM_PATH;
if(process.env.CHROMIUM_ARGS)options.args=JSON.parse(process.env.CHROMIUM_ARGS);
(async()=>{
 const browser=await chromium.launch(options),context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[];
 page.on('pageerror',e=>{errors.push(e.message);console.error('Browser error:',e.message);});
 page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
 // Expected, UI-handled 422: a one-version procedure has nothing to compare, so the impact-review panel shows its own note. Only that exact response is allowed; any other console error still fails.
 let expected422=0;
 page.on('response',async r=>{if(!r.url().includes('/api/')||r.status()<400)return;const body=await r.text().catch(()=>'');if(r.status()===422&&/\/api\/knowledge\/[^/?]+\/impact-review$/.test(r.url())&&/Choose two retained versions/.test(body)){expected422++;return}console.error('API error',r.status(),r.url(),body);});
 const visible=locator=>locator.waitFor({state:'visible',timeout:180000});
 const goto=async p=>{await page.goto(base+p);await page.waitForLoadState('networkidle');};
 try{
  await goto('/');await visible(page.getByRole('heading',{name:/Every issue/}));
  await page.screenshot({path:path.join(out,'landing-desktop.png'),fullPage:true});
  await page.getByRole('button',{name:'Explore a sample case',exact:true}).first().click();
  await page.waitForURL('**/workspace');await visible(page.getByRole('heading',{name:"Overview"}));
  console.log('PASS: public landing and isolated sample onboarding');
  await goto('/workspace/cases/CASE-4');await page.getByRole('button',{name:'Run investigation',exact:true}).click();
  await visible(page.getByRole('heading',{name:'Investigation findings'}));
  await page.getByLabel('Review notes',{exact:true}).fill('Reviewed the cited procedure and historical synthetic records.');
  await page.getByRole('button',{name:'Approve recommendation'}).click();
  await visible(page.getByText('approved by Sample visitor',{exact:true}));
  const pdfDownload = page.waitForEvent('download');
  await page.getByRole('button',{name:'Download PDF report',exact:true}).click();
  const pdf = await pdfDownload;
  await pdf.saveAs(path.join(out,'investigation-report.pdf'));
  assert(fs.readFileSync(path.join(out,'investigation-report.pdf')).subarray(0,5).equals(Buffer.from('%PDF-')));
  console.log('PASS: authenticated investigation PDF download through web proxy');

  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:path.join(out,'investigation-desktop.png'),fullPage:false});
  const prepared = await page.evaluate(async()=>{
   async function call(path,body){const r=await fetch('/api'+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw new Error(JSON.stringify(d));return d;}
   const detail=await call('/cases/CASE-4'),rid=detail.runs[0].id;
   const e=await call('/cases/CASE-4/evidence',{id:crypto.randomUUID(),kind:'human_observation',summary:'Browser test personally verified current synthetic binder records.',observed_at:new Date().toISOString()});
   let c=await call('/runs/'+rid+'/checks',{});c=await call('/cases/CASE-4/checks/'+c.id+'/activate',{expected_version:c.version});
   c.items.forEach(i=>{i.state='verified';i.notes='Current synthetic record manually verified.';i.evidence_refs=[e.id]});
   await call('/cases/CASE-4/checks/'+c.id,{expected_version:c.version,items:c.items});return e.id;
  });
  await goto('/workspace/cases/CASE-4');
  await page.getByLabel('Resolution supporting evidence',{exact:true}).selectOption(prepared);
  const verification=new Date();await page.getByLabel('Current verification time',{exact:true}).fill(new Date(verification.getTime()-verification.getTimezoneOffset()*60000).toISOString().slice(0,19));
  await page.getByLabel('Resolution note',{exact:true}).fill('Synthetic demo: verified the necessary current checks and completed the case.');
  await page.getByRole('checkbox',{name:/I verified current status/}).check();await page.getByRole('button',{name:'Mark case resolved',exact:true}).click();
  await visible(page.getByText('Case marked resolved.',{exact:true}));
  await page.getByLabel('Reason for reopening',{exact:true}).fill('Reopen the synthetic case to verify updated operational conditions.');
  await page.getByRole('button',{name:'Reopen case',exact:true}).click();
  await visible(page.getByText('Case reopened; the original resolution remains in activity.',{exact:true}));
  console.log('PASS: investigation, review, manual resolution, and reopening');
  await goto('/workspace/cases/CASE-7');await page.getByRole('button',{name:'Run investigation',exact:true}).click();
  await visible(page.getByText('Insufficient relevant evidence. Approval is unavailable.',{exact:true}));
  assert.equal(await page.getByRole('button',{name:'Approve recommendation'}).isDisabled(),true);
  await page.getByLabel('Review notes',{exact:true}).fill('No relevant operational evidence supports the cafeteria question.');
  await page.getByRole('button',{name:'Reject',exact:true}).click();await visible(page.getByText('rejected by Sample visitor',{exact:true}));
  console.log('PASS: unsupported evidence blocks approval and permits rejection');
  await goto('/workspace/knowledge');
  await page.getByLabel('Upload procedure file').setInputFiles({name:'Sample shipping procedure.txt',mimeType:'text/plain',buffer:Buffer.from('Verify the synthetic shipment tracking receipt and the recorded dispatch status. Ask a reviewer before drafting any supplier escalation. Do not change source records.')});
  await visible(page.getByText(/characters extracted/));
  await page.getByRole('button',{name:'Save procedure',exact:true}).click();await visible(page.getByText(/Procedure saved/));
  assert(await page.getByRole('button',{name:/Sample shipping procedure.*v1/}).count());
  console.log('PASS: upload, extraction preview, and versioned knowledge save');
  await goto('/workspace/new');await page.getByLabel('Issue title',{exact:true}).fill('Uploaded certificates missing from binder');
  await page.getByLabel('Describe the issue',{exact:true}).fill('Synthetic training certificates were uploaded yesterday but remain missing. A monitoring visit is tomorrow and review is blocked.');
  await page.getByRole('button',{name:'Suggest classification',exact:true}).click();await visible(page.getByText(/Suggested:/));
  await page.getByRole('button',{name:'Use suggestion',exact:true}).click();
  await page.getByLabel(/^Study/).selectOption('CT-204');await page.getByLabel(/^Site/).selectOption('SITE-104');
  await page.getByRole('button',{name:'Create case',exact:true}).click();await page.waitForURL('**/workspace/cases/CASE-*');
  await visible(page.getByRole('heading',{name:'Uploaded certificates missing from binder',exact:true}));
  console.log('PASS: reviewed classification, dependent sites, and case creation');
  await goto('/workspace/feedback');await page.getByLabel('Your feedback',{exact:true}).fill('The workflow is easy to navigate. Evidence and human decisions are clear.');
  await page.getByRole('button',{name:'Submit feedback',exact:true}).click();await visible(page.getByText(/Your feedback was saved/));
  await goto('/workspace/settings');await page.getByRole('button',{name:'Workspace & team',exact:true}).click();const downloading=page.waitForEvent('download');
  await page.getByRole('button',{name:'Export workspace records',exact:true}).click();const download=await downloading;
  await download.saveAs(path.join(out,'workspace-export.json'));const exported=JSON.parse(fs.readFileSync(path.join(out,'workspace-export.json'),'utf8'));assert(exported.runs.length===2);
  console.log('PASS: feedback and workspace export');
  await page.getByRole('button',{name:'Studies & sites',exact:true}).click();
  await page.getByLabel('New study ID',{exact:true}).fill('CT-BROWSER');
  await page.getByLabel('Study name',{exact:true}).fill('Synthetic browser study');
  await page.getByRole('button',{name:'Add study',exact:true}).click();await visible(page.getByText('Study context created.',{exact:true}));
  await page.getByLabel('New site ID',{exact:true}).fill('SITE-BROWSER');
  await page.getByLabel('Site name',{exact:true}).fill('Synthetic browser site');
  await page.getByLabel('Site study',{exact:true}).selectOption('CT-BROWSER');
  await page.getByRole('button',{name:'Add site',exact:true}).click();await visible(page.getByText('Site context created and linked to the selected study.',{exact:true}));
  await goto('/workspace/new');await page.getByLabel(/^Study/).selectOption('CT-BROWSER');await page.getByLabel(/^Site/).selectOption('SITE-BROWSER');
  console.log('PASS: custom study/site creation and availability in dependent intake selectors');

  for(const width of [1440,1024,768,390]){
    await page.setViewportSize({width,height:900});await goto('/workspace');
    const metrics=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));assert(metrics.scroll<=metrics.width+1,JSON.stringify(metrics));
    if(width===390){await page.getByRole('button',{name:/Menu/}).click();assert.equal(await page.getByRole('navigation',{name:'Workspace navigation'}).getByRole('link').count(),9);await page.getByRole('link',{name:'Feedback',exact:true}).click();await visible(page.getByRole('heading',{name:'Share feedback',exact:true}));await goto('/workspace');assert(await page.getByRole('button',{name:'Sign out',exact:true}).isVisible());}
    if(width===390)await page.screenshot({path:path.join(out,'workspace-mobile.png'),fullPage:true});
  }
  await page.setViewportSize({width:390,height:844});await goto('/');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.screenshot({path:path.join(out,'landing-mobile.png'),fullPage:true});
  assert.deepEqual(errors.filter(e=>!(expected422>0&&/status of 422/.test(e)&&expected422--)),[]);
  const blocked=await page.request.post(base+'/api/feedback',{headers:{Origin:'https://wrong-origin.invalid'},data:{rating:5,message:'Cross origin should be blocked'}});assert.equal(blocked.status(),403);
  console.log('PASS: four responsive widths, no uncaught browser errors, and cross-origin write blocking');
 }catch(e){await page.screenshot({path:path.join(out,'failure.png'),fullPage:true});throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
