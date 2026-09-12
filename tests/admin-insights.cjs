const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),path=require('node:path');
const client=(slug,name,strategy,profit,stale=false)=>({slug,name,data:{accounts:[{slug:strategy,name:strategy,balance:100,usd_brl_rate:5,stale,growth_series:[{date:'7/1/2026',profit:100,value:100},{date:'9/9/2026',profit,value:200}]}],total_balance:100,total_profit_month:profit,stale}});
const fixture={clients:[client('ana','Ana','Gold',-5,true),client('bruno','Bruno','Portfolio',20),{slug:'missing',name:'Sem histórico',error:'Indisponível'}],health:{ok:1,stale:2,stale_accounts:[]}};
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 const context=await browser.newContext({viewport:{width:1440,height:1000}});await context.addInitScript(()=>localStorage.setItem('copytrader_admin_token','fixture'));
 let queries=0;await context.route('**/*',route=>{const u=new URL(route.request().url());if(u.hostname==='cdnjs.cloudflare.com')return route.fulfill({contentType:'text/javascript',body:'window.Chart=class{constructor(el,c){this.data=c.data}destroy(){}};'});if(u.hostname!=='k4-preview.test')return route.abort();if(u.pathname==='/admin/summary'){queries++;return route.fulfill({json:fixture})}return route.fulfill({path:path.resolve(__dirname,'../frontend',u.pathname.startsWith('/static/')?path.basename(u.pathname):'index.html')})});
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('http://k4-preview.test/admin');await page.locator('#insightTotal').filter({hasText:'15,00'}).waitFor();
 assert((await page.locator('#insightCoverage').innerText()).includes('2 de 3'));
 assert.deepEqual(await page.evaluate(()=>adminInsightChart.data.datasets[0].data),[0,15]);
 assert.equal(await page.locator('#insightAlerts .insight-alert').count(),3);
 await page.locator('#insightPeriods [data-days="0"]').click();assert.deepEqual(await page.evaluate(()=>adminInsightChart.data.datasets[0].data),[0,200,215]);
 await page.locator('#insightPeriods [data-days="30"]').click();
 await page.locator('#insightCurrency').selectOption('brl');assert((await page.locator('#insightTotal').innerText()).includes('75,00'));
 await page.locator('#insightClient').selectOption('ana');assert.equal(await page.evaluate(()=>adminInsightChart.data.datasets[0].data.at(-1)),-25);
 await page.locator('#insightAlertType').selectOption('loss');assert.equal(await page.locator('#insightAlerts .insight-alert').count(),1);
 await page.locator('#insightAlerts button').click();assert(await page.locator('#adm_name_ana').isVisible());
 await page.locator('#insightClient').selectOption('missing');assert.equal(await page.locator('#insightTotal').innerText(),'—');assert(await page.locator('#insightEmpty').isVisible());
 await page.locator('#insightClient').selectOption('');await page.locator('#insightStrategy').selectOption('Portfolio');assert((await page.locator('#insightTotal').innerText()).includes('100,00'));
 for(const width of [1440,1100,390]){await page.setViewportSize({width,height:1000});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Overflow at '+width)}
 assert.equal(queries,1);assert.deepEqual(errors,[]);console.log('PASS: consolidação, períodos, moedas, filtros, alertas, dados ausentes e navegação; sem consultas extras.');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
