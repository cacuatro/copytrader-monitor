// Run with PLAYWRIGHT_MODULE pointing to an installed playwright package.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const series=Array.from({length:150},(_,i)=>{const date=new Date(Date.UTC(2026,3,1+i));return {date:`${date.getUTCMonth()+1}/${date.getUTCDate()}/${date.getUTCFullYear()}`,value:i/10,profit:2}}).filter((_,i)=>i%7!==0);
const account={slug:'gold',name:'Gold Dragon',balance:1000,balance_brl:5000,profit_week:21,profit_week_brl:105,profit_month:-12,profit_month_brl:-60,profit_total:150,profit_total_brl:750,growth_series:series,history:[]};
const client={slug:'ana',name:'Ana Costa',accounts:[account],total_balance:1000,total_balance_brl:5000,total_profit_week:21,total_profit_month:-12,total_profit_total:150,usd_brl_rate:5,notice_history:[]};
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 await context.addInitScript(()=>localStorage.setItem('copytrader_token_ana','fixture-token'));
 let queries=0;const errors=[];
 await context.route('**/*',route=>{
  const u=new URL(route.request().url());
  if(u.hostname==='cdnjs.cloudflare.com')return route.fulfill({contentType:'text/javascript',body:'window.Chart=class {constructor(el,c){this.data=c.data}destroy(){}};'});
  if(u.hostname!=='k4-preview.test')return route.abort();
  if(u.pathname==='/cliente/ana'){queries++;return route.fulfill({json:client})}
  if(u.pathname.startsWith('/static/'))return route.fulfill({path:path.resolve(__dirname,'../frontend',path.basename(u.pathname))});
  return route.fulfill({path:path.resolve(__dirname,'../frontend/index.html')});
 });
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://k4-preview.test/ana');await page.locator('#clientName').filter({hasText:'Ana'}).waitFor();
 assert.equal(await page.locator('#chartPeriods .a').innerText(),'Total');
 assert.equal(await page.evaluate(()=>chartInst.data.labels.length),series.length);
 assert.equal(await page.locator('#sWithdrawalsCommission,#sPaidCommissions').count(),0);
 assert(await page.locator('#app header .brand-emblem').evaluate(img=>img.complete&&img.naturalWidth>0));
 assert.equal(await page.locator('.support-metrics .sm').count(),1);
 const stats=await page.locator('#cards .sc-stats').innerText();
 for(const text of ['Saldo','Resultado na semana','21,00','Resultado em 30 dias','12,00','Resultado total','150,00'])assert(stats.includes(text),text);
 for(const days of [7,30,90]){
  await page.locator(`#chartPeriods [data-days="${days}"]`).click();
  const end=Date.parse(series.at(-1).date+' UTC'),expected=series.filter(p=>Date.parse(p.date+' UTC')>=end-(days-1)*86400000).length;
  assert.equal(await page.evaluate(()=>chartInst.data.labels.length),expected+1);
  const values=await page.evaluate(()=>chartInst.data.datasets[0].data);assert.equal(values[0],0);assert.equal(values[1],.2);assert(Math.abs(values.at(-1)-expected*.2)<1e-9);
 }
 await page.locator('#cards .sc').click();assert.equal(await page.locator('#chartPeriods .a').innerText(),'90 dias');
 await page.locator('#chartPeriods [data-days="0"]').click();assert.equal(await page.evaluate(()=>chartInst.data.labels.length),series.length);
 await page.locator('#cards .sc').click();assert.equal(await page.locator('#chartPeriods .a').innerText(),'Total');
 await page.getByRole('button',{name:'Moeda: USD'}).click();
 const converted=await page.locator('#cards .sc-stats').innerText();for(const n of ['105,00','60,00','750,00'])assert(converted.includes(n));
 assert.equal(queries,1,'Changing period, strategy and currency must reuse loaded data');
 const isolated=await page.evaluate(()=>{
  const data={balance:100,growth_series:[{date:'8/1/2026',value:250,profit:250},{date:'9/8/2026',value:248,profit:-2},{date:'9/9/2026',value:245,profit:-3},{date:'9/10/2026',value:246,profit:1}]};
  return {window:chartResultSeries(data,7).map(p=>p.value),total:chartResultSeries(data,0).map(p=>p.value),noBalance:chartResultSeries({...data,balance:0},7),noData:chartResultSeries({...data,growth_series:[]},7),oneDay:chartResultSeries({...data,growth_series:[data.growth_series[1]]},7).map(p=>p.value)};
 });
 assert.deepEqual(isolated.window,[0,-2,-5,-4],'Exclude older gains, include the first day and retain losses');
 assert.deepEqual(isolated.total,[250,248,245,246],'Total retains the complete accumulated history');
 assert.deepEqual(isolated.noBalance,[]);assert.deepEqual(isolated.noData,[]);assert.deepEqual(isolated.oneDay,[0,-2]);

 await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.evaluate(()=>render({...currentData,data_unavailable:true,total_balance:null,accounts:[{slug:'missing',name:'Sem dados',error:'Indisponivel'}]}));
 assert.equal(await page.locator('#sBalance').innerText(),'—');
 assert.deepEqual(errors,[]);
 console.log('PASS: Total inicial, intervalos por data, troca de estratégia, moeda, semana/total, ausência de saques/comissões e dados indisponíveis.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
