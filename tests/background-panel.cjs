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
  let syncing=true; const errors=[],apiRequests=[];
  await context.route('**/*',route=>{
   const url=new URL(route.request().url());
   if(url.hostname==='cdnjs.cloudflare.com')return route.fulfill({contentType:'text/javascript',body:'window.Chart=class {destroy(){}};'});
   if(url.hostname!=='k4-preview.test')return route.abort();
   if(url.pathname==='/admin/summary'){apiRequests.push(url.pathname);const response=structuredClone(fixture);response.refreshing=syncing;if(!syncing)response.clients[0].data.total_balance=15000;return route.fulfill({json:response})}
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
  await page.locator('#adm_name_bruno').fill('Nome em edição');
  assert(await page.locator('#backgroundRefresh').isVisible());
  syncing=false;
  await page.waitForFunction(()=>document.getElementById('aBalance').textContent.includes('23.000,00'),{},{timeout:15000});
  assert(await page.locator('#adm_name_bruno').isVisible());
  assert.equal(await page.locator('#adm_name_bruno').inputValue(),'Nome em edição');
  assert(!(await page.locator('#backgroundRefresh').isVisible()));
  for(const id of ['aDay','aWeek','aTotal'])assert(await page.locator('#'+id).isVisible());
  const periods=await page.locator('[data-client-slug="ana"] .record-results').innerText();
  for(const label of ['Hoje','Semana','30 dias','Total'])assert(periods.includes(label));
  assert.equal(apiRequests.length,2);
  assert.deepEqual(errors,[]);
  console.log('PASS: dados salvos aparecem antes da atualização; polling recebe valores novos, preserva edição e exibe os quatro períodos.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
