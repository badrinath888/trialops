// Uses a fresh, expiring sample workspace; never signs into an existing account.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const base = require('./target.cjs')();
const out = process.env.TEST_SCREENSHOT_DIR || path.resolve(__dirname, '../../artifacts/ui-review');
fs.mkdirSync(out, { recursive: true });
(async () => {
 const options = {headless:true};
 if(process.env.CHROMIUM_PATH) options.executablePath = process.env.CHROMIUM_PATH;
 if(process.env.CHROMIUM_ARGS) options.args = JSON.parse(process.env.CHROMIUM_ARGS);
 const browser = await chromium.launch(options);
 const context = await browser.newContext({viewport:{width:1440,height:900}});
 const page = await context.newPage(), report = {pages:[], interactions:[], errors:[]};
 page.on('pageerror', e => report.errors.push(e.message));
 const go = async route => {await page.goto(base + route); await page.waitForLoadState('networkidle');};
 const capture = async name => {
  await page.mouse.move(0,0);
  await page.screenshot({path:path.join(out,name+'.png'),fullPage:true,animations:'disabled'});
  const metrics = await page.evaluate(() => {
   const rgba = s => (s.match(/[\d.]+/g)||[]).map(Number);
   const blend = (a,b) => a.slice(0,3).map((v,i)=>v*(a[3]??1)+b[i]*(1-(a[3]??1)));
   const lum = c => c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
   const issues=[], smallControls=[], tinyText=[]; let count=0;
   const walk=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;
   while(n=walk.nextNode()) {
    const e=n.parentElement, text=n.textContent.trim();if(!text||!e||e.closest('script,style,svg,option')||(text==='✳'&&e.closest('.wordmark')))continue;
    const s=getComputedStyle(e), r=e.getBoundingClientRect();if(!r.width||!r.height||s.visibility==='hidden'||e.closest('[hidden]'))continue;
    const range=document.createRange();range.selectNodeContents(n);if(!range.getBoundingClientRect().width)continue;
    const size=parseFloat(s.fontSize);if(size<15)tinyText.push({text:text.slice(0,60),size});
    const chain=[];for(let p=e;p;p=p.parentElement)chain.unshift(p);
    let bg=[255,255,255], uncertain=false;for(const p of chain){const ps=getComputedStyle(p);if(ps.backgroundImage!=='none'||ps.opacity!=='1')uncertain=true;bg=blend(rgba(ps.backgroundColor),bg);}
    if(uncertain)continue;
    const fg=blend(rgba(s.color),bg),l1=lum(fg),l2=lum(bg),ratio=(Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05);
    const threshold=size>=24||(size>=18.66&&parseInt(s.fontWeight)>=700)?3:4.5;
    count++;if(ratio<threshold&&!e.closest(':disabled'))issues.push({text:text.slice(0,75),ratio:+ratio.toFixed(2),color:s.color,bg,size});
   }
   for(const e of document.querySelectorAll('button,a.button,input:not([type=checkbox]):not([type=radio]),select')){const r=e.getBoundingClientRect();if(r.width&&r.height&&!e.closest('[hidden]')&&r.height<43)smallControls.push({text:e.textContent.trim().slice(0,60),height:r.height});}
   return {width:innerWidth,scrollWidth:document.documentElement.scrollWidth,contrastChecked:count,contrastIssues:issues,tinyText,smallControls};
  });
  report.pages.push({name,url:page.url(),...metrics});
 };
 try {
  for(const width of [1440,390]){await page.setViewportSize({width,height:900});for(const [name,route] of [['landing','/'],['sign-in','/sign-in'],['register','/sign-in?mode=register'],['guide','/guide']]){await go(route);await capture(name+'-'+width);}}
  await page.setViewportSize({width:1440,height:900});await go('/');await page.getByRole('button',{name:'Explore a sample case',exact:true}).first().click();await page.waitForURL('**/workspace');await page.waitForLoadState('networkidle');
  assert(await page.getByText(/Sample workspace · expires/).count());
  const me=await (await page.request.get(base+'/api/auth/me')).json();report.sampleWorkspace=me.workspace_id;
  await go('/workspace/cases/CASE-4');await page.getByRole('button',{name:'Run investigation',exact:true}).click();await page.getByRole('heading',{name:'Investigation findings',exact:true}).waitFor({timeout:180000});await page.getByLabel('Review notes',{exact:true}).fill('Synthetic UI review: checked procedure and historical evidence.');await page.getByRole('button',{name:'Approve recommendation',exact:true}).click();await page.getByText('approved by Sample visitor',{exact:true}).waitFor();report.interactions.push('Sample investigation and human approval');const runPath=await page.getByRole('link',{name:'Open saved investigation →',exact:true}).getAttribute('href');
  await go('/workspace/roi');await page.getByLabel('Approved investigation',{exact:true}).selectOption({index:1});await page.getByRole('checkbox').check();await page.getByRole('button',{name:'Save scenario',exact:true}).click();await page.getByText('Scenario saved. These values are assumptions, not measured savings.',{exact:true}).waitFor();report.interactions.push('Confirmed sample ROI scenario saves');
  await go('/workspace/operations');await page.getByLabel('Snapshot JSON',{exact:true}).fill('{invalid}');await page.getByRole('button',{name:'Validate and save snapshot',exact:true}).click();await page.getByRole('alert').filter({hasText:'Invalid JSON.'}).waitFor();await capture('snapshot-validation');await page.getByRole('button',{name:'Load example format',exact:true}).click();await page.getByRole('status').filter({hasText:'Example format loaded'}).waitFor();await page.getByRole('button',{name:'Validate and save snapshot',exact:true}).click();await page.getByRole('status').filter({hasText:'New investigations use this snapshot.'}).waitFor();report.interactions.push('Invalid snapshot error and valid sample import');
  const routes=[['overview','/workspace'],['cases','/workspace/cases'],['case-detail','/workspace/cases/CASE-4'],['saved-investigation',runPath],['new','/workspace/new'],['knowledge','/workspace/knowledge'],['history','/workspace/history'],['operations','/workspace/operations'],['roi','/workspace/roi'],['feedback','/workspace/feedback'],['settings','/workspace/settings']];
  for(const width of [1440,390]){
   await page.setViewportSize({width,height:900});
   for(const [name,route] of routes){await go(route);await capture(name+'-'+width);if(name==='case-detail'||name==='saved-investigation'){for(const tab of ['Evidence','Records','Activity']){await page.getByRole('tab',{name:tab,exact:true}).click();await capture(name+'-findings-'+tab+'-'+width);}await page.getByRole('tab',{name:'Activity',exact:true}).press('Home');assert.equal(await page.getByRole('tab',{name:'Overview',exact:true}).getAttribute('aria-selected'),'true');}
    if(name==='knowledge'){await page.getByRole('button',{name:/Uploaded training certificate.*v1/}).click();await capture('procedure-detail-'+width);}
    if(name==='settings'){for(const section of ['Workspace & team','Studies & sites','Data policy']){await page.getByRole('button',{name:section,exact:true}).click();await capture('settings-'+section.replaceAll(' ','-')+'-'+width);}}}
  }
  await go('/workspace/cases');const tableScroll=page.locator('.data-table-wrap');await tableScroll.focus();await page.keyboard.press('ArrowRight');await page.waitForTimeout(250);assert(await tableScroll.evaluate(e=>e.scrollLeft>0));report.interactions.push('Narrow cases table scrolls with keyboard');
  await go('/workspace');await page.getByRole('button',{name:/Menu/}).click();await capture('mobile-menu');assert.equal(await page.getByRole('navigation',{name:'Workspace navigation'}).getByRole('link').count(),9);await page.getByRole('navigation',{name:'Workspace navigation'}).getByRole('link').first().focus();await page.keyboard.press('Escape');assert(await page.getByRole('button',{name:/Menu/}).evaluate(e=>e===document.activeElement));report.interactions.push('Mobile menu: nine routes, Escape returns focus');
  await page.setViewportSize({width:1440,height:620});await go('/workspace');await page.locator('.sidebar').evaluate(e=>e.scrollTop=e.scrollHeight);const box=await page.getByRole('button',{name:'Sign out',exact:true}).boundingBox();assert(box.y>=0&&box.y+box.height<=620);await capture('sidebar-short');report.interactions.push('Short desktop sidebar independently scrolls to Sign out');
  await go('/workspace/cases');await page.getByLabel('Search cases').fill('case 4');await page.waitForFunction(()=>{const r=document.querySelectorAll('.data-table tbody tr');return r.length===1&&r[0].textContent.includes('CASE-4')&&!document.body.innerText.includes('Loading cases…')},null,{timeout:15000});assert.equal(await page.locator('.data-table tbody tr').count(),1);const preview=page.getByRole('button',{name:'Preview CASE-4',exact:true});await preview.click();await page.getByRole('dialog').waitFor();await capture('case-preview');await page.keyboard.press('Escape');assert(await preview.evaluate(e=>e===document.activeElement));report.interactions.push('Case search alias, preview, Escape and focus return');
  await go('/workspace/settings');await page.getByRole('group',{name:'Content spacing',exact:true}).getByRole('radio',{name:'Comfortable',exact:true}).check();await page.getByRole('button',{name:'Save preferences',exact:true}).click();await page.reload();await page.waitForLoadState('networkidle');assert(await page.locator('.app-shell').evaluate(e=>e.classList.contains('density-comfortable')));report.interactions.push('Sample account preferences save and persist');
  await go('/workspace/new');assert(await page.getByRole('button',{name:'Create case',exact:true}).isDisabled());report.interactions.push('Empty intake cannot submit');
  assert.deepEqual(report.errors,[]);
  for(const p of report.pages){assert(p.scrollWidth<=p.width+1,p.name+' page overflow');assert.deepEqual(p.tinyText,[],p.name+' text below 15px');assert.deepEqual(p.smallControls,[],p.name+' controls below 44px');assert.deepEqual(p.contrastIssues,[],p.name+' computed text contrast');}
 } finally {fs.writeFileSync(path.join(out,'computed-review.json'),JSON.stringify(report,null,2));await browser.close();}
 console.log(JSON.stringify({pages:report.pages.length,interactions:report.interactions,issues:report.pages.filter(p=>p.scrollWidth>p.width+1||p.contrastIssues.length||p.tinyText.length||p.smallControls.length)},null,2));
})().catch(e=>{console.error(e);process.exitCode=1});
