// Reference layout: presentation only, preserving the existing API and controls.
const iconPaths={wallet:'M3 6h16v14H3z M3 6V3h13v3 M15 11h6v5h-6z',chart:'M4 20V12h3v8 M10 20V7h3v13 M16 20V3h3v17',trend:'M3 17l6-6 4 3 7-9 M14 5h6v6',calendar:'M4 5h16v16H4z M8 2v6 M16 2v6 M4 10h16',users:'M16 21v-3c0-3-3-4-6-4s-6 1-6 4v3 M10 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M17 4a4 4 0 0 1 0 7 M19 15c2 1 2 3 2 6',coins:'M4 6c0-5 16-5 16 0s-16 5-16 0 M4 6v12c0 5 16 5 16 0V6 M4 12c0 5 16 5 16 0',refresh:'M20 8a9 9 0 0 0-15-3L2 8 M2 2v6h6 M4 16a9 9 0 0 0 15 3l3-3 M22 22v-6h-6',home:'M3 11l9-8 9 8 M5 10v11h5v-7h4v7h5V10',notice:'M3 10v5h5l11 5V5L8 10z M7 15l2 7',audit:'M6 3h12v19H6z M9 8h6 M9 12h6 M9 16h4',exchange:'M3 7h18l-4-4 M21 17H3l4 4',percent:'M5 20L19 4 M6 4a2 2 0 1 0 0 4 2 2 0 0 0 0-4 M18 16a2 2 0 1 0 0 4 2 2 0 0 0 0-4'};
function uiIcon(name){return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${iconPaths[name]||iconPaths.chart}"/></svg>`}
function initials(name){return String(name||'').trim().split(/\s+/).slice(0,2).map(n=>n[0]).join('').toUpperCase()}
function accountStatus(c){return c.error||!c.data||c.data.data_unavailable?'missing':c.data.stale?'stale':'fresh'}
renderAdminClient=function(c,period='month',strategyFilter=''){
 const d=c.data||{},state=accountStatus(c),missing=state==='missing',pv=periodValue(d,period);
 const names=(d.accounts||[]).map(a=>a.name).filter(Boolean).join(', ');
 return `<details class="client-record" data-client-slug="${esc(c.slug)}"><summary><div class="record-name"><span class="avatar">${esc(initials(c.name))}</span><span>${esc(c.name)}<small>${esc(c.username||'')}</small></span></div><div class="record-strategies">${esc(names||'Sem dados')}</div><div class="record-balance">${missing?'—':fmtBalance(d.total_balance)}</div><div class="record-results">${[['Hoje','day'],['Semana','week'],['30 dias','month'],['Total','total']].map(([label,key])=>`<div><small>${label}</small><span class="${missing?'n':col(d['total_profit_'+key])}">${missing?'—':fmtMoney(d['total_profit_'+key])}</span></div>`).join('')}</div><div class="record-date">${esc(savedDate(d.last_success_at))}</div><div class="record-status ${state}"><span class="status-dot"></span>${missing?'Indisponível':state==='stale'?'Dados salvos':'Atualizado'}</div><span class="record-toggle">Ver</span></summary>${originalRenderAdminClient(c,period,strategyFilter)}</details>`;
};
const referenceRenderAdmin=renderAdmin;
function updateStrategyFilter(d){
 const select=document.getElementById('filterStrategy'),selected=select.value;
 const names=[...new Set((d.clients||[]).flatMap(c=>(c.data?.accounts||[]).map(a=>a.name).filter(Boolean)))].sort((a,b)=>a.localeCompare(b,'pt-BR'));
 select.replaceChildren(new Option('Todas as estratégias',''),...names.map(name=>new Option(name,name.toLowerCase())));
 if(names.some(name=>name.toLowerCase()===selected))select.value=selected;
}
function clearAdminFilters(){
 for(const id of ['filterClient','filterStrategy','filterStatus'])document.getElementById(id).value='';
 if(adminData)renderAdmin(adminData);
}
renderAdmin=function(d){updateStrategyFilter(d);referenceRenderAdmin(d);const h=d.health||{};document.getElementById('syncCounts').innerHTML=`<span class="sync-chip fresh">${Number(h.ok)||0} atualizadas</span><span class="sync-chip stale">${Number(h.stale)||0} precisam de atenção</span>`;document.getElementById('adminAvatar').textContent='AD';showBackgroundRefresh(d);scheduleSnapshotPoll(d);};
const referenceRenderClient=render;
render=function(d){referenceRenderClient(d);document.getElementById('clientAvatar').textContent=initials(d.name);document.getElementById('clientSub').textContent='Acompanhe seus resultados.';showBackgroundRefresh(d);scheduleSnapshotPoll(d);};
const referenceCards=renderCards;
renderCards=function(){referenceCards();document.querySelectorAll('#cards .sc').forEach((card,i)=>{const a=allAccounts[i];if(a.error)return;const top=card.querySelector('.sc-top');top.insertAdjacentHTML('afterbegin',`<span class="strategy-icon">${uiIcon(/gold/i.test(a.name)?'trend':'chart')}</span>`);const stats=card.querySelector('.sc-stats');stats.innerHTML=`<div><div class="ss-l">Saldo</div><div class="ss-v n">${currencyMode==='brl'?fmtBrl(a.balance_brl):fmtBalance(a.balance)}</div></div><div><div class="ss-l">Resultado na semana</div><div class="ss-v ${col(a.profit_week)}">${fmtCurrency(a.profit_week,a.profit_week_brl)}</div></div><div><div class="ss-l">Resultado em 30 dias</div><div class="ss-v ${col(a.profit_month)}">${fmtCurrency(a.profit_month,a.profit_month_brl)}</div></div><div><div class="ss-l">Resultado total</div><div class="ss-v ${col(a.profit_total)}">${fmtCurrency(a.profit_total,a.profit_total_brl)}</div></div>`;card.insertAdjacentHTML('beforeend','<span class="strategy-link">Ver detalhes →</span>');card.tabIndex=0;card.setAttribute('role','button');card.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();card.click()}})})};
function referenceLayout(){
 document.body.classList.add('reference-layout');
 document.querySelectorAll('#app header .logo,#admin header .logo').forEach(el=>el.innerHTML='<div class="brand-lockup"><img class="brand-emblem" src="/static/logo.png" alt="Logo K4 Trader" width="56" height="56"><div class="wordmark"><span>K4</span> Trader</div></div>');
 const clientMain=document.querySelector('#app main');clientMain.id='clientOverview';
 document.getElementById('clientName').insertAdjacentHTML('beforebegin','<div class="eyebrow">ÁREA DO CLIENTE</div>');
 document.getElementById('clientSub').insertAdjacentHTML('afterend','<blockquote class="brand-quote">“Disciplina hoje,<br>mais liberdade amanhã.”<small>K4 TRADER</small></blockquote>');
 const nav=document.createElement('nav');nav.className='client-nav';nav.innerHTML='<a href="#clientOverview">Visão geral</a><a href="#clientStrategies">Estratégias</a><a href="#clientHistory">Histórico</a>';document.querySelector('#app header .logo').after(nav);
 document.querySelector('#app .head-actions').insertAdjacentHTML('afterbegin','<span class="avatar" id="clientAvatar"></span>');
 document.querySelector('#admin .head-actions').insertAdjacentHTML('afterbegin','<span class="avatar" id="adminAvatar">AD</span><span class="admin-identity">Admin<small>Administrador</small></span>');
 const summary=clientMain.querySelector('.summary');const short=document.createElement('div');short.className='short-metrics';for(const id of ['sDay','sWeek'])short.append(document.getElementById(id).closest('.sm'));summary.append(short);
 const cards=document.getElementById('cards'),label=cards.previousElementSibling;const strategies=document.createElement('section');strategies.id='clientStrategies';strategies.className='strategy-section detail';cards.before(strategies);strategies.innerHTML='<div class="detail-head"><div><div class="detail-title">Suas estratégias</div><div class="detail-sub">Confira o desempenho de cada estratégia em sua conta.</div></div><a class="all-strategies-link" href="https://k4-monitor.copytraderk4.workers.dev/estrategias" target="_blank" rel="noopener noreferrer">Ver todas as estratégias do copy <span aria-hidden="true">→</span></a></div>';strategies.append(cards);if(label?.classList.contains('sec-label'))label.remove();
 document.getElementById('histBody').closest('.detail').id='clientHistory';
 const icons={sBalance:'wallet',sMonth:'chart',sTotal:'trend',sDay:'calendar',sWeek:'calendar',sUsdBrl:'exchange',aClients:'users',aBalance:'wallet',aMonth:'chart',aCommMonth:'coins'};
 for(const [id,name] of Object.entries(icons)){const card=document.getElementById(id).closest('.sm');card.classList.add('icon-metric');card.insertAdjacentHTML('afterbegin',`<span class="metric-icon">${uiIcon(name)}</span>`)}
 document.getElementById('aBalance').previousElementSibling.textContent='Saldo monitorado';document.getElementById('aMonth').previousElementSibling.textContent='Resultado em 30 dias';document.getElementById('aCommMonth').previousElementSibling.textContent='Comissões em 30 dias';
 const sidebar=document.querySelector('.admin-sidebar');sidebar.insertAdjacentHTML('afterbegin','<div class="brand-lockup"><img class="brand-emblem" src="/static/logo.png" alt="Logo K4 Trader" width="56" height="56"><div class="wordmark"><span>K4</span> Trader</div></div>');['home','users','refresh','notice','audit'].forEach((name,i)=>sidebar.querySelectorAll('a')[i].insertAdjacentHTML('afterbegin',uiIcon(name)));
 const adm=document.querySelector('#admin main'),health=document.getElementById('monitorHealth');
 health.querySelector('.detail-title').textContent='Atenção necessária';
 const diag=document.createElement('details');diag.className='diagnostic-disclosure';diag.innerHTML='<summary>Diagnóstico da integração</summary>';diag.append(document.getElementById('myfxbookDiagnostics'),health.lastElementChild);health.append(diag);
 const sync=document.createElement('div');sync.className='sync-strip';sync.innerHTML=`${uiIcon('refresh')}<strong>Sincronização das contas</strong><div id="syncCounts"></div>`;adm.querySelector('.summary').after(sync);
 const clientRows=document.getElementById('adminClients'),filters=document.getElementById('filterClient').closest('.detail');filters.classList.add('client-toolbar');filters.querySelector('.detail-title').textContent='Clientes';filters.querySelector('.detail-sub').remove();filters.querySelector('.detail-head>button').remove();
 const refresh=health.querySelector('button');refresh.classList.add('primary-action');refresh.textContent='↻ Atualizar dados';filters.querySelector('.admin-stats').prepend(refresh);
 const status=document.createElement('select');status.id='filterStatus';status.className='login-input';status.setAttribute('aria-label','Filtrar status');status.innerHTML='<option value="">Todos os status</option><option value="fresh">Atualizado</option><option value="stale">Dados salvos</option><option value="missing">Indisponível</option>';filters.querySelector('.admin-stats').append(status);status.addEventListener('change',()=>adminData&&renderAdmin(adminData));document.getElementById('filterStrategy').addEventListener('change',()=>adminData&&renderAdmin(adminData));
 const clear=document.createElement('button');clear.id='clearAdminFilters';clear.className='tab';clear.type='button';clear.textContent='Limpar filtros';clear.addEventListener('click',clearAdminFilters);filters.querySelector('.admin-stats').append(clear);
 const section=document.createElement('section');section.className='clients-section';section.id='clientsSection';clientRows.before(section);if(section.previousElementSibling?.classList.contains('sec-label'))section.previousElementSibling.remove();section.append(filters);section.insertAdjacentHTML('beforeend','<div class="client-columns"><span>Cliente</span><span>Estratégias</span><span>Saldo</span><span>Resultados</span><span>Últimos dados</span><span>Status</span><span>Ações</span></div>');section.append(clientRows);sync.after(section);
 const bottom=document.createElement('div');bottom.className='admin-bottom';section.after(bottom);bottom.append(health,document.getElementById('adminNotices'));
 const extra=document.querySelector('.additional-metrics');bottom.after(extra);
 const periods=document.createElement('div');periods.className='admin-period-results';
 for(const id of ['aDay','aWeek','aTotal'])periods.append(document.getElementById(id).closest('.sm'));
 adm.querySelector('.summary').after(periods);
 extra.querySelector('summary').textContent='Outras comissões';
 document.getElementById('auditBody').closest('div').removeAttribute('id');document.getElementById('auditBody').closest('.detail').id='adminAudit';
 for(const main of [clientMain,adm])main.insertAdjacentHTML('beforeend','<footer class="dashboard-footer"><span>K4 Trader</span><span>Disciplina para ir mais longe.</span></footer>');
 syncChartPeriod();
}
let snapshotTimer=null;
function showBackgroundRefresh(d){
 const root=document.querySelector(isAdminPath?'#admin main':'#app main');
 let status=document.getElementById('backgroundRefresh');
 if(!status){status=document.createElement('div');status.id='backgroundRefresh';status.className='sync-banner';status.setAttribute('role','status');root.querySelector('.client-sub').after(status)}
 status.hidden=!d.refreshing;
 status.textContent='Atualizando em segundo plano… Os últimos dados disponíveis permanecem na tela.';
}
function scheduleSnapshotPoll(d){
 clearTimeout(snapshotTimer);
 if(!d.refreshing||!authToken)return;
 const token=authToken;
 snapshotTimer=setTimeout(async()=>{
  if(authToken!==token)return;
  try{
   const response=await fetch(API_BASE+(isAdminPath?'/admin/summary':'/cliente/'+encodeURIComponent(currentSlug)),{headers:{Authorization:'Bearer '+token}});
   if(authToken!==token)return;
   if(response.status===401||response.status===403){logout();return}
   if(!response.ok)throw new Error('Refresh failed');
   const next=await response.json();
   const fields=[...document.querySelectorAll('#adminClients input,#adminClients textarea,#clientProfile input')].map(el=>[el.id,el.value]);
   const open=[...document.querySelectorAll('.client-record[open]')].map(el=>el.dataset.clientSlug);
   const focused=document.activeElement?.id,selected=selectedAcc;
   if(isAdminPath){renderAdmin(next);document.querySelectorAll('.client-record').forEach(el=>el.open=open.includes(el.dataset.clientSlug))}
   else{render(next);if(selected&&allAccounts.some(a=>a.slug===selected&&!a.error)){selectedAcc=selected;renderCards();renderDetail(activeAccount())}}
   for(const [id,value] of fields){const el=document.getElementById(id);if(el)el.value=value}
   if(focused)document.getElementById(focused)?.focus({preventScroll:true});
  }catch(e){if(authToken===token)scheduleSnapshotPoll(d)}
 },5000);
}
referenceLayout();

load();
