// Run: PLAYWRIGHT_MODULE=<path to playwright> node tests/admin-client-details.cjs
// All account data and API responses below are fictional and local to this test.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const frontend=path.resolve(__dirname,'../frontend');
const sample=(slug,name,strategy,balance)=>({slug,name,username:slug,data:{slug,name,accounts:[{slug:strategy,name:strategy,balance,growth_series:[]}],total_balance:balance,total_profit_day:1,total_profit_week:7,total_profit_month:30,total_profit_total:40,commission_day:.3,commission_week:2.1,commission_month:9,commission_total:12,last_success_at:'2026-09-10T18:00:00Z'}});
const fixture={clients:[sample('ana','Ana Costa','Gold Dragon',12000),sample('bruno','Bruno Lima','Portfolio',8000)],health:{ok:2,stale:0},global_notices:[],access_logs:[],audit_logs:[]};
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  await context.addInitScript(()=>localStorage.setItem('copytrader_admin_token','fixture-token'));
  const errors=[],apiRequests=[];
  await context.route('**/*',route=>{
   const url=new URL(route.request().url());
   if(url.hostname==='cdnjs.cloudflare.com')return route.fulfill({contentType:'text/javascript',body:'window.Chart=class {destroy(){}};'});
   if(url.hostname!=='k4-preview.test')return route.abort();
   if(url.pathname==='/admin/summary'){apiRequests.push(url.pathname);return route.fulfill({json:fixture})}
   if(url.pathname.startsWith('/static/'))return route.fulfill({path:path.join(frontend,path.basename(url.pathname))});
   return route.fulfill({path:path.join(frontend,'index.html')});
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://k4-preview.test/admin');
  await page.locator('[data-client-slug="ana"]').waitFor();
  assert.equal(await page.locator('#filterStrategy').evaluate(el=>el.tagName),'SELECT');
  assert.equal(await page.locator('#aClients').innerText(),'2');
  // Clicking either the name or Ver opens the same client's information.
  await page.locator('[data-client-slug="ana"] .record-toggle').click();
  assert(await page.locator('#adm_name_ana').isVisible());
  assert.equal(await page.locator('#adm_name_ana').inputValue(),'Ana Costa');
  assert.equal(await page.locator('#adm_pass_ana').getAttribute('autocomplete'),'new-password');
  assert.equal(await page.locator('#filterStrategy').inputValue(),'');
  assert.equal(await page.locator('#aClients').innerText(),'2');
  await page.locator('[data-client-slug="ana"] .record-name').click();
  assert(!(await page.locator('#adm_name_ana').isVisible()));
  await page.locator('[data-client-slug="bruno"] .record-name').click();
  assert.equal(await page.locator('#adm_name_bruno').inputValue(),'Bruno Lima');
  assert(await page.locator('#adm_name_bruno').isVisible());
  // A saved login value cannot become an arbitrary strategy option.
  await page.locator('#filterStrategy').evaluate(el=>{el.value='admin';el.dispatchEvent(new Event('change',{bubbles:true}))});
  assert.equal(await page.locator('#aClients').innerText(),'2');
  await page.locator('#filterStrategy').selectOption('gold dragon');
  assert.equal(await page.locator('#aClients').innerText(),'1');
  assert.equal(await page.locator('.client-record').count(),1);
  await page.locator('[data-client-slug="ana"] .record-toggle').click();
  assert(await page.locator('#adm_name_ana').isVisible());
  assert.equal(await page.locator('#filterStrategy').inputValue(),'gold dragon');
  await page.locator('#filterClient').fill('admin');
  assert.equal(await page.locator('#aClients').innerText(),'0');
  await page.locator('#clearAdminFilters').click();
  assert.equal(await page.locator('#aClients').innerText(),'2');
  for(const width of [1440,1100,390]){
   await page.setViewportSize({width,height:1000});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`overflow at ${width}`);
  }
  await page.locator('[data-client-slug="ana"]>summary').focus();
  await page.keyboard.press('Enter');
  assert(await page.locator('#adm_name_ana').isVisible());
  assert.equal(apiRequests.length,1,'Details and filters must not request new account data');
  assert.deepEqual(errors,[]);
  console.log('PASS: Ver/nome/teclado abrem o cliente correto; filtro de estratégias, limpar filtros, totais e 3 larguras; sem novas consultas.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
