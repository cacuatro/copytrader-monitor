// Administration insights use saved account data only; no extra upstream calls.
let adminInsightChart=null,adminInsightDays=30;
function insightDate(value){const [month,day,year]=String(value||'').split('/').map(Number);return month&&day&&year?Date.UTC(year,month-1,day):NaN}
function insightMoney(value,brl){return new Intl.NumberFormat('pt-BR',{style:'currency',currency:brl?'BRL':'USD'}).format(value)}
function insightRows(d){
 const client=document.getElementById('insightClient').value,strategy=document.getElementById('insightStrategy').value;
 return (d.clients||[]).filter(c=>!client||c.slug===client).flatMap(c=>{
  const accounts=c.data?.accounts||[];
  return (accounts.length?accounts:[{name:'Contas indisponíveis',error:c.error||'Sem dados'}]).filter(a=>!strategy||a.name===strategy).map(a=>({client:c,account:a}));
 });
}
function insightData(rows,days,brl){
 const seen=new Set(),accounts=rows.filter(({client,account:a})=>{const key=a.slug||client.slug+':'+a.name;if(seen.has(key))return false;seen.add(key);return true});
 const usable=accounts.filter(({account:a})=>!a.error&&(a.growth_series||[]).some(p=>Number.isFinite(insightDate(p.date))&&p.profit!=null&&Number.isFinite(Number(p.profit)))&&(!brl||Number(a.usd_brl_rate)>0));
 const all=usable.flatMap(({account:a})=>a.growth_series.map(p=>insightDate(p.date)).filter(Number.isFinite));
 const end=all.length?Math.max(...all):NaN,start=days?end-(days-1)*86400000:-Infinity;
 const dates=new Map(),losses=[];let included=0;
 for(const row of usable){const a=row.account,rate=brl?Number(a.usd_brl_rate):1;let result=0,count=0;
  for(const p of a.growth_series){const t=insightDate(p.date);if(!Number.isFinite(t)||t<start||t>end||p.profit==null||!Number.isFinite(Number(p.profit)))continue;const profit=Number(p.profit)*rate;dates.set(t,(dates.get(t)||0)+profit);result+=profit;count++}
  if(count){included++;if(result<0)losses.push({...row,result})}
 }
 let total=0;const points=[...dates].sort((a,b)=>a[0]-b[0]).map(([time,profit])=>({time,value:total+=profit}));
 return {points,total,included,accounts:accounts.length,losses};
}
function setInsightOptions(id,values,label){const el=document.getElementById(id),old=el.value;el.replaceChildren(new Option(label,''),...values.map(([value,name])=>new Option(name,value)));if(values.some(([value])=>value===old))el.value=old}
function openAlertClient(slug){clearAdminFilters();const row=[...document.querySelectorAll('.client-record')].find(el=>el.dataset.clientSlug===slug);if(row){row.open=true;row.scrollIntoView({behavior:'smooth',block:'center'})}}
function renderAdminInsights(d){
 if(!document.getElementById('adminInsightCanvas'))return;
 setInsightOptions('insightClient',(d.clients||[]).map(c=>[c.slug,c.name]),'Todos os clientes');
 const selected=document.getElementById('insightClient').value;
 const names=[...new Set((d.clients||[]).filter(c=>!selected||c.slug===selected).flatMap(c=>(c.data?.accounts||[]).map(a=>a.name).filter(Boolean)))].sort();
 setInsightOptions('insightStrategy',names.map(n=>[n,n]),'Todas as estratégias');
 const rows=insightRows(d),brl=document.getElementById('insightCurrency').value==='brl',data=insightData(rows,adminInsightDays,brl);
 document.getElementById('insightTotal').textContent=data.points.length?insightMoney(data.total,brl):'—';
 document.getElementById('insightTotal').className=data.total<0?'r':'g';
 const range=data.points.length?' · '+new Date(data.points[0].time).toLocaleDateString('pt-BR',{timeZone:'UTC'})+' a '+new Date(data.points.at(-1).time).toLocaleDateString('pt-BR',{timeZone:'UTC'}):'';
 document.getElementById('insightCoverage').textContent=`${data.included} de ${data.accounts} contas com histórico no período${data.included<data.accounts?' · Resultado parcial':''}${range}. Soma dos resultados diários salvos${brl?', convertidos pela cotação salva de cada conta':''}.`;
 document.getElementById('insightEmpty').hidden=!!data.points.length;
 document.getElementById('adminInsightCanvas').parentElement.hidden=!data.points.length;
 if(adminInsightChart)adminInsightChart.destroy();
 const color=data.total<0?'#ed786d':'#14d6aa';
 adminInsightChart=new Chart(document.getElementById('adminInsightCanvas'),{type:'line',data:{labels:data.points.length?['Início',...data.points.map(p=>new Date(p.time).toLocaleDateString('pt-BR',{timeZone:'UTC'}))]:[],datasets:[{label:'Resultado no período',data:data.points.length?[0,...data.points.map(p=>round2(p.value))]:[],borderColor:color,backgroundColor:color+'20',fill:'origin',borderWidth:2,pointRadius:0,pointHoverRadius:6,pointHoverBorderWidth:2,pointHoverBorderColor:'#ffffff',pointBackgroundColor:color,tension:.2}]},options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:'index',axis:'x',intersect:false},plugins:{legend:{display:false},tooltip:{enabled:true,mode:'index',intersect:false,backgroundColor:'#0c1713',titleColor:'#ffffff',bodyColor:'#e0eee8',padding:12,displayColors:false,callbacks:{label:ctx=>insightMoney(ctx.parsed.y,brl)}}},scales:{x:{ticks:{color:'#a4adb0',maxTicksLimit:8},grid:{color:'#ffffff08'}},y:{ticks:{color:'#a4adb0',callback:value=>insightMoney(value,brl)},grid:{color:'#ffffff08'}}}}});
 const alerts=[];
 for(const {client:c,account:a} of rows){
  const issue=(d.health?.stale_accounts||[]).find(h=>h.client===c.name&&(!h.strategy||h.strategy===a.name));
  if(a.error)alerts.push({slug:c.slug,title:a.refreshing?'Sincronização em andamento':'Conta indisponível',detail:c.name+' · '+a.name,kind:a.refreshing?'stale':'missing'});
  else if(a.stale||issue)alerts.push({slug:c.slug,title:a.refreshing?'Atualizando dados salvos':'Dados desatualizados',detail:c.name+' · '+a.name+' · '+(issue?.reason||'Última consulta: '+savedDate(a.fetched_at)),kind:'stale'});
 }
 for(const {client:c,account:a,result} of data.losses)alerts.push({slug:c.slug,title:'Resultado negativo no período',detail:c.name+' · '+a.name+' · '+insightMoney(result,brl),kind:'missing'});
 const chosen=document.getElementById('insightAlertType').value;
 const visible=alerts.filter(a=>!chosen||(chosen==='loss'?a.title==='Resultado negativo no período':a.title!=='Resultado negativo no período'));
 document.getElementById('insightAlertCount').textContent=alerts.length+' alerta(s) nos filtros selecionados';
 const body=document.getElementById('insightAlerts');body.innerHTML=visible.map(a=>`<div class="insight-alert"><span class="status-dot ${a.kind}"></span><div><strong>${esc(a.title)}</strong><small>${esc(a.detail)}</small></div><button type="button" class="tab" data-client="${esc(a.slug)}">Ver cliente</button></div>`).join('')||'<div class="empty">Nenhum alerta nos filtros selecionados.</div>';
 body.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>openAlertClient(b.dataset.client)));
}
function setupAdminInsights(){
 const graph=document.createElement('section');graph.className='detail admin-insights';graph.id='adminInsights';
 graph.innerHTML='<div class="detail-head"><div><div class="detail-title">Evolução do resultado</div><div class="detail-sub">Lucro e prejuízo acumulados dentro do período selecionado</div></div><strong id="insightTotal">—</strong></div><div class="insight-controls"><label>Cliente<select id="insightClient" class="login-input"></select></label><label>Estratégia<select id="insightStrategy" class="login-input"></select></label><label>Moeda<select id="insightCurrency" class="login-input"><option value="usd">US$</option><option value="brl">R$</option></select></label><div class="tabs" id="insightPeriods"></div></div><div id="insightCoverage" class="detail-sub"></div><div class="chart-wrap"><canvas id="adminInsightCanvas"></canvas></div><div id="insightEmpty" class="empty" hidden>Sem histórico disponível para este período.</div>';
 document.querySelector('.admin-period-results').after(graph);
 const periods=graph.querySelector('#insightPeriods');for(const [days,label] of [[7,'7 dias'],[30,'30 dias'],[90,'90 dias'],[0,'Total']]){const b=document.createElement('button');b.type='button';b.className='tab'+(days===30?' a':'');b.textContent=label;b.dataset.days=days;b.setAttribute('aria-pressed',String(days===30));b.addEventListener('click',()=>{adminInsightDays=days;periods.querySelectorAll('button').forEach(el=>{const active=Number(el.dataset.days)===days;el.classList.toggle('a',active);el.setAttribute('aria-pressed',String(active))});if(adminData)renderAdminInsights(adminData)});periods.append(b)}
 const alerts=document.createElement('section');alerts.className='detail';alerts.id='adminAlerts';alerts.innerHTML='<div class="detail-head"><div><div class="detail-title">Central de alertas</div><div class="detail-sub" id="insightAlertCount"></div></div><select class="login-input" id="insightAlertType" aria-label="Tipo de alerta"><option value="">Todos os alertas</option><option value="sync">Sincronização</option><option value="loss">Resultados negativos</option></select></div><div class="detail-sub">Acompanha os filtros e o período do gráfico acima.</div><div id="insightAlerts"></div>';
 graph.after(alerts);
 for(const id of ['insightClient','insightStrategy','insightCurrency','insightAlertType'])document.getElementById(id).addEventListener('change',()=>adminData&&renderAdminInsights(adminData));
 const link=document.createElement('a');link.href='#adminAlerts';link.innerHTML=uiIcon('notice')+'Alertas';document.querySelector('.admin-sidebar').append(link);
}
