'use strict';
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
$('#signal-motion-toggle')?.addEventListener('click', event => {
  const button = event.currentTarget;
  const paused = button.getAttribute('aria-pressed') !== 'true';
  button.setAttribute('aria-pressed', String(paused));
  button.textContent = paused ? 'Resume motion' : 'Pause motion';
  button.closest('.signal-instrument').dataset.paused = String(paused);
});
let report=null, reportTime=null, sizing=null, riskRevision=0, previousIntent='help';
let currentBars=null, currentSymbol='', currentFile='', currentConfig=null;
let quantResult=null, councilResult=null, portfolio=null, scenarioResult=null, capabilities=null;
let previousConversation=null;
let pullbackResult=null, pullbackDataRevision=-1;
let learningResult=null;
let liveEvidence=null;
let portfolioBusy=false, datasetRevision=0, portfolioRevision=0, toastTimer=null, finceptStatus=null, pendingImportFile=null;
const storageKey='loki-fusion-paper-v1';
const pct = value => value==null || !Number.isFinite(Number(value)) ? '—' : `${(Number(value)*100).toFixed(2)}%`;
const pctPoints = value => value==null || !Number.isFinite(Number(value)) ? '—' : `${Number(value).toFixed(2)}%`;
const pctSigned = value => value==null || !Number.isFinite(Number(value)) ? '—' : `${Number(value)>=0?'+':'−'}${Math.abs(Number(value)).toFixed(2)}%`;
const number = (value,digits=2) => value==null || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString(undefined,{maximumFractionDigits:digits});
const numericForm = form => Object.fromEntries([...new FormData(form)].map(([key,value])=>[key,Number(value)]));
const human = value => String(value??'').replaceAll('_',' ').replaceAll('-',' ');
function element(tag,text,className){const node=document.createElement(tag);if(text!=null)node.textContent=text;if(className)node.className=className;return node;}
function message(selector,text,error=false){const target=$(selector);target.textContent=text;target.classList.toggle('error',error);}
function newsPacket(read){
  // The desk news agent's read, reduced to the council's bounded JSON
  // contract: score, count, scored headlines, method. Inspection evidence
  // only — the council validates it strictly and no gate consults it.
  if(!read||read.status!=='ok'||typeof read.score!=='number')return null;
  const rows=(Array.isArray(read.top)?read.top:[])
    .filter(row=>row&&typeof row.title==='string'&&row.title.length>=3&&typeof row.score==='number')
    .slice(0,30)
    .map(row=>({title:row.title,publisher:String(row.publisher||''),score:row.score}));
  if(!rows.length)return null;
  const counted=Number.isInteger(read.headlines_read)?read.headlines_read:rows.length;
  return {status:'ok',score:read.score,headlines_read:Math.min(50,Math.max(1,counted)),top:rows,method:String(read.method||'')};
}
const COUNCIL_HISTORY_KEY='loki_council_history_v1',COUNCIL_HISTORY_MAX=12;
function readCouncilHistory(){
  // The day's verdicts, kept in this browser only. Old or malformed rows
  // are skipped, never guessed at: a broken record is simply not history.
  try{const raw=JSON.parse(localStorage.getItem(COUNCIL_HISTORY_KEY)||'[]');return Array.isArray(raw)?raw.filter(row=>row&&typeof row.at==='number'&&typeof row.symbol==='string'&&typeof row.decision==='string').slice(0,COUNCIL_HISTORY_MAX):[];}catch(_e){return[];}
}
function pushCouncilHistory(row){
  // Newest first, capped; a refused write skips the feature, nothing else.
  try{const list=readCouncilHistory();list.unshift(Object.assign({at:Date.now()},row));localStorage.setItem(COUNCIL_HISTORY_KEY,JSON.stringify(list.slice(0,COUNCIL_HISTORY_MAX)));}catch(_e){}
}
function renderCouncilHistory(selector){
  const target=$(selector);if(!target)return;
  const rows=readCouncilHistory();
  if(!rows.length){target.replaceChildren();const empty=element('p','No reviews recorded in this browser yet — convene one above; it lands here the moment it answers.','muted');empty.style.margin='0';target.append(empty);return;}
  target.replaceChildren(...rows.map(row=>{
    const li=element('li',null,'council-history-row');
    li.append(element('small',new Date(row.at).toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}),'council-history-at'));
    li.append(element('strong',row.symbol+(row.source?' · '+human(row.source):''),'council-history-symbol'));
    li.append(element('span',human(row.decision)+(row.blocked?' · '+row.blocked+' blocked check'+(row.blocked===1?'':'s'):' · every gate passed'),'council-history-detail'));
    return li;
  }));
}
function clearCouncilHistory(){
  try{localStorage.removeItem(COUNCIL_HISTORY_KEY);}catch(_e){}
  renderCouncilHistory('#council-history');renderCouncilHistory('#desk-council-history');
}
function toast(text){$('#toast').textContent=text;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>{$('#toast').hidden=true;},4500);}
async function request(url,payload,privileged=false){
  const headers={'Accept':'application/json'};if(payload!==undefined)headers['Content-Type']='application/json';
  if(privileged&&capabilities?.local_token)headers['X-Loki-Local-Token']=capabilities.local_token;
  const response=await fetch(url,{method:payload===undefined?'GET':'POST',headers,body:payload===undefined?undefined:JSON.stringify(payload),cache:'no-store'});
  let data;try{data=await response.json();}catch{throw new Error(`The server returned ${response.status}. Try again after checking the service.`);}
  if(!response.ok){const tidy=(text)=>String(text).replace(/^body\.([A-Za-z_]+): /,(_match,field)=>`The ${field.replace(/_/g,' ')} field: `);const detail=data.detail??data.message??data.error;throw new Error(typeof detail==='string'?tidy(detail):Array.isArray(detail)?detail.map(item=>tidy(`${item.loc?.join('.')||'Input'}: ${item.msg||item}`)).join('\n'):detail?JSON.stringify(detail):`Request failed (${response.status}).`);}
  if(data?.success===false)throw new Error(data.message||data.error||'The external service could not complete this request.');
  return data;
}
const post=(url,payload)=>{
  if(url==='/api/copilot'&&window.lokiSimulatedMarket?.snapshot()){const sim=window.lokiSimulatedMarket.snapshot();payload={...payload,context:{...payload.context,simulated_market:{quotes:sim.quotes,metrics:sim.metrics,step:sim.state.step,scenario:sim.state.scenario,synthetic:true}}};}
  if(url==='/api/fusion/council'){const miroId=$('#miro-native-id').value.trim(),reviewed=$('#miro-native-reviewed').checked;if(miroId){if(!/^report_[A-Za-z0-9_-]+$/.test(miroId)||!reviewed)throw new Error('The native MiroFish report is not ready to travel with this review: inspect a valid report_ id and tick the reviewed confirmation first.');return request(url,{...payload,miro_report_id:miroId,miro_reviewed:true},true);}}
  if(url==='/api/copilot'&&window.lokiBrokerWorkspace?.summary())payload={...payload,context:{...payload.context,broker_connection:window.lokiBrokerWorkspace.summary()}};
  if(url==='/api/copilot'&&learningResult)payload={...payload,context:{...payload.context,market_learning:learningResult}};
  if(url==='/api/copilot'&&pullbackResult&&pullbackDataRevision===datasetRevision)payload={...payload,context:{...payload.context,pullback_research:pullbackResult}};
  return request(url,payload);
};
$('#miro-native-id').addEventListener('input',()=>{$('#miro-native-reviewed').checked=false;$('#miro-native-preview').replaceChildren();message('#miro-native-message','');});
$('#inspect-native-report').addEventListener('click',async()=>{const id=$('#miro-native-id').value.trim();if(!/^report_[A-Za-z0-9_-]+$/.test(id)){message('#miro-native-message','Enter a native report_ identifier.',true);return;}const button=$('#inspect-native-report');button.disabled=true;try{const result=await request(`/api/fusion/native-mirofish/report/${encodeURIComponent(id)}?symbol=${encodeURIComponent(currentSymbol||'BTC/USDT')}`,undefined,true),report=result.report,target=$('#miro-native-preview');target.replaceChildren(element('h3',report.outline.title),element('p',report.outline.summary),bulletList(report.outline.sections.slice(0,8).map(s=>`${s.title}: ${(s.content||'').slice(0,800)}`)),detailsJSON(result,'Inspect complete native report & provenance'));message('#miro-native-message',`Read directly through MiroFish code · ${report.simulation_id} · ${report.graph_id} · ${result.artifact_sha256.slice(0,12)}. ${result.timestamp_note}`);}catch(error){message('#miro-native-message',error.message,true);}finally{button.disabled=false;}});
function table(headers,rows){const result=element('table'),head=element('thead'),headRow=element('tr');for(const title of headers)headRow.append(element('th',title));head.append(headRow);result.append(head);const body=element('tbody');for(const values of rows){const row=element('tr');for(const value of values){const td=element('td');if(value instanceof Node)td.append(value);else td.textContent=value??'—';row.append(td);}body.append(row);}result.append(body);return result;}
function bulletList(items){const list=element('ul');for(const text of items||[])list.append(element('li',String(text)));return list;}
function inlineMetrics(items){const container=element('div',null,'inline-metrics');for(const [label,value,note]of items){const node=element('div',null,'inline-metric');node.append(element('span',label),element('strong',value));if(note)node.append(element('small',note));container.append(node);}return container;}
function badge(text,status){return element('span',human(text),'tag '+(status||''));}
function detailsJSON(data,label='Inspect complete result'){const details=element('details',null,'source-details');details.append(element('summary',label),element('pre',JSON.stringify(data,null,2)));return details;}
function exportJSON(data,filename){const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=element('a');a.href=url;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function exportWorkspace(){exportJSON({application:'Loki Fusion',exported_at:new Date().toISOString(),mode:'paper_research',dataset:currentBars?{symbol:currentSymbol,file:currentFile,bars:currentBars}:null,research:report,quant:quantResult,pullback:pullbackResult,market_learning:learningResult,council:councilResult,portfolio,scenario:scenarioResult,synthetic_practice:window.lokiSimulatedMarket?.snapshot()||null},`loki-workspace-${new Date().toISOString().slice(0,10)}.json`);}

$('#train-history').addEventListener('click',async()=>{
  const button=$('#train-history');button.disabled=true;message('#learning-message','Fetching public history and fitting training dates only…');
  try{
    const result=await post('/api/fusion/learn-history',{});learningResult=result;
    const target=$('#learning-results');target.replaceChildren();target.hidden=false;
    target.append(inlineMetrics([['Historical dates',number(result.observations,0),`${result.coverage.start} → ${result.coverage.end}`],['Training examples',number(result.training.examples,0),`Labels through ${result.training.end}`],['Test direction accuracy',pct(result.test.direction_accuracy),`${result.test.examples} later predictions · not trade wins`],['Constant-model accuracy',pct(result.test.training_majority_baseline_accuracy),'Baseline selected on training dates']]));
    target.append(element('p',`${human(result.status)}. Trading win rate remains unproven.`, 'integration-note'));
    const scroll=element('div',null,'table-scroll');scroll.append(table(['Period','Examples','Direction accuracy','Brier error ↓','Baseline Brier ↓'],[['Validation',result.validation.examples,pct(result.validation.direction_accuracy),number(result.validation.brier_score,4),number(result.validation.baseline_brier_score,4)],['Test',result.test.examples,pct(result.test.direction_accuracy),number(result.test.brier_score,4),number(result.test.baseline_brier_score,4)]]));target.append(scroll,bulletList(result.limitations),detailsJSON(result,'Inspect model weights, source, dates & all metrics'));
    const download=element('button','Export trained research model ↓','button secondary');download.type='button';download.addEventListener('click',()=>exportJSON(result,'loki-market-research-model.json'));target.append(download);
    message('#learning-message',`Completed · ${result.source.attribution} Model ${result.artifact_sha256.slice(0,12)}.`);
  }catch(error){message('#learning-message',error.message,true);}finally{button.disabled=false;}
});

// Every section uses the same in-memory dataset and paper journal.
function navigate(){const aliases={'risk-studio':'portfolio'};const hash=location.hash.slice(1)||'overview';let view=aliases[hash]||hash;if(!$('#'+CSS.escape(view))?.classList.contains('workspace-view'))view='overview';
  $$('.workspace-view').forEach(section=>{section.hidden=section.id!==view;});
  const frame=$('#'+CSS.escape(view)+' iframe[data-src]');if(frame&&!frame.getAttribute('src'))frame.src=frame.dataset.src;
  $$('.sidebar nav a').forEach(link=>{const active=link.dataset.view===view;link.classList.toggle('active',active);if(active)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');});
  const moreGroup=$('#nav-more-group'),moreBtn=$('#nav-more-toggle');
  if(moreGroup&&moreBtn&&moreGroup.querySelector(`a[data-view="${view}"]`)){moreGroup.hidden=false;moreBtn.setAttribute('aria-expanded','true');}
  $('#page-name').textContent=$(`.sidebar nav a[data-view="${view}"]`).textContent.trim().replace(/^\S+\s+/,'');document.title=`Loki · ${$('#page-name').textContent}`;
  document.dispatchEvent(new CustomEvent('loki:view',{detail:{view}}));
  requestAnimationFrame(()=>{if(hash==='risk-studio')$('#risk-studio').scrollIntoView();else window.scrollTo({top:0,behavior:'instant'});drawChart();});
}
window.addEventListener('hashchange',navigate);
(function bindMore(){
  const button=$('#nav-more-toggle'),group=$('#nav-more-group');
  if(!button||!group)return;
  button.addEventListener('click',()=>{const open=group.hidden;group.hidden=!open;button.setAttribute('aria-expanded',String(open));});
})();
function syncContext(){
  if(pullbackDataRevision!==datasetRevision){pullbackResult=null;$('#pullback-results').hidden=true;message('#pullback-message','Uses the active imported history. New datasets clear the previous candidate result.');}
  $('#workspace-context').hidden=!currentBars;$('#context-status').textContent=currentBars?`${currentSymbol} · ${currentBars.length.toLocaleString()} bars`:'No dataset';
  $('#sidebar-symbol').textContent=currentSymbol||'No asset loaded';$('#sidebar-data').textContent=currentBars?`${currentBars.length.toLocaleString()} bars · ${report?.status==='paper_candidate'?'paper candidate':'research loaded'}`:'Import history in Quant lab';
  $('#context-symbol').textContent=currentSymbol;$('#context-detail').textContent=currentBars?`${currentBars[0].timestamp.slice(0,10)} → ${currentBars.at(-1).timestamp.slice(0,10)} · imported history · not live`:'';
  $('#chat-context-status').textContent=report?`${currentSymbol} · research loaded`:'No research loaded';
  $('#council-context').textContent=currentBars?`${currentSymbol} · ${currentBars.length.toLocaleString()} bars`:'Your research is the starting point.';
  $('#council-context-detail').textContent=report?`Walk-forward report ${report.data_fingerprint?.slice(0,12)||''} · ${report.summary.total_trades} closed trades · ${report.status==='paper_candidate'?'paper candidate':'further evidence needed'}`:'Import a dataset in Quant lab. The council evaluates that history and your current paper portfolio.';
}
function csvRows(text){const rows=[];let row=[],value='',quoted=false;for(let i=0;i<text.length;i++){const char=text[i];if(char==='"'){if(quoted&&text[i+1]==='"'){value+='"';i++;}else quoted=!quoted;}else if(char===','&&!quoted){row.push(value.trim());value='';}else if((char==='\n'||char==='\r')&&!quoted){if(char==='\r'&&text[i+1]==='\n')i++;row.push(value.trim());if(row.some(Boolean))rows.push(row);row=[];value='';}else value+=char;}if(quoted)throw new Error('CSV has an unclosed quoted field.');row.push(value.trim());if(row.some(Boolean))rows.push(row);return rows;}
function parseBars(text){const rows=csvRows(text.replace(/^\uFEFF/,''));const headers=(rows.shift()||[]).map(value=>value.toLowerCase());const required=['timestamp','open','high','low','close','volume'];if(required.some(key=>!headers.includes(key))||new Set(headers).size!==headers.length)throw new Error('Use unique CSV columns: timestamp, open, high, low, close, volume.');if(rows.length<161||rows.length>5000)throw new Error('Upload between 161 and 5,000 bars from one asset.');return rows.map((row,index)=>{if(row.length!==headers.length)throw new Error(`CSV row ${index+2} has the wrong number of columns.`);const bar={};for(const key of required){const raw=row[headers.indexOf(key)];if(!raw)throw new Error(`CSV row ${index+2}: ${key} is empty.`);if(key==='timestamp')bar[key]=raw;else{const value=Number(raw);if(!Number.isFinite(value))throw new Error(`CSV row ${index+2}: ${key} must be a number.`);bar[key]=value;}}return bar;});}
function renderReport(){const metrics=report.summary;$('#return-metric').textContent=pct(metrics.total_return);$('#return-metric').className=metrics.total_return>=0?'positive':'negative';$('#drawdown-metric').textContent=pct(metrics.max_drawdown);$('#winrate-metric').textContent=pct(metrics.win_rate);$('#trades-metric').textContent=`${metrics.total_trades} closed trades · 95% interval ${metrics.win_rate_ci95?metrics.win_rate_ci95.map(pct).join('–'):'unavailable'}`;$('#verdict-metric').textContent=report.status==='paper_candidate'?'Paper candidate':'More evidence needed';$('#research-details').hidden=false;
  $('#research-summary').replaceWith(Object.assign(inlineMetrics([['Out-of-sample return',pct(metrics.total_return),'After estimated trading costs'],['Closed-trade win rate',pct(metrics.win_rate),`${metrics.total_trades} closed trades`],['Maximum drawdown',pct(metrics.max_drawdown),'Across unseen test windows']]),{id:'research-summary'}));
  $('#evidence-list').replaceChildren(...[...(report.rejection_reasons||[]),...(report.assumptions||[])].map(reason=>element('li',reason)));
  $('#stress-table').replaceChildren(table(['Cost multiplier','Net return','Drawdown'],(report.cost_stress||[]).map(s=>[`${s.multiplier}×`,pct(s.total_return),pct(s.max_drawdown)])));
  const regime=report.regime_metrics;
  if(regime?.rows?.length){$('#regime-panel').hidden=false;$('#regime-note').textContent=regime.rules;$('#regime-table').replaceChildren(table(['Regime','Bars','Share','Strategy P&L','Buy&hold P&L','Trades closed in it','Average trade'],regime.rows.map(row=>[row.regime,number(row.bars,0),pctPoints(row.share_pct),pctSigned(row.strategy_contribution_pct),pctSigned(row.benchmark_contribution_pct),number(row.trades_closed_in_bucket,0),row.average_trade_pnl==null?'—':number(row.average_trade_pnl)])));}
  else if($('#regime-panel')){$('#regime-panel').hidden=true;}
  const folds=$('#fold-table');folds.replaceChildren();for(const fold of report.folds||[]){const row=element('tr');for(const value of [fold.test_start.slice(0,10),fold.test_end.slice(0,10),JSON.stringify(fold.parameters),pct(fold.metrics.total_return)])row.append(element('td',value));folds.append(row);}
  $('#report-statistics').textContent=`Expectancy: ${number(metrics.expectancy)} / trade · Profit factor: ${metrics.profit_factor==null?'not estimable':number(metrics.profit_factor)} · Fees: ${number(metrics.total_fees)} · Slippage: ${number(metrics.total_slippage)} · ${report.trial_count} training trials`;
  $('#chart-empty').hidden=true;$('#equity-chart').hidden=false;$('#chart-caption').textContent=`Historical forward tests: ${report.test_start.slice(0,10)} → ${report.test_end.slice(0,10)} · ${report.bars} supplied bars · Fingerprint ${report.data_fingerprint.slice(0,16)}… · Input quote currency · Benchmarks use the same dates and the same cost assumptions: buy-and-hold (dashed line) and cash (flat at start). Every result carries its window, config, fees, slippage and fingerprint — export it any time.`;drawChart();renderRunSummary();renderPinStrip();
}
function drawChart(){
  if(!report||$('#overview').hidden)return;
  const canvas=$('#equity-chart'),width=canvas.clientWidth;if(!width)return;
  const height=canvas.clientHeight||280,scale=window.devicePixelRatio||1;
  canvas.width=Math.round(width*scale);canvas.height=Math.round(height*scale);
  const ctx=canvas.getContext('2d');ctx.setTransform(scale,0,0,scale,0,0);
  ctx.clearRect(0,0,width,height);
  const points=[{timestamp:report.test_start,equity:report.config.initial_capital,benchmark_equity:report.config.initial_capital},...report.equity_curve];
  const values=points.flatMap(point=>[point.equity,point.benchmark_equity]);
  const min=Math.min(...values),max=Math.max(...values),padding=Math.max((max-min)*.12,max*.005,1),low=min-padding,high=max+padding;
  const left=width<520?52:64,right=54,top=16,bottom=30;
  const plotW=Math.max(1,width-left-right),plotH=Math.max(1,height-top-bottom);
  const x=i=>left+(points.length<=1?0:i/Math.max(1,points.length-1))*plotW;
  const y=value=>top+(high-value)/(high-low)*plotH;
  const mono='"JetBrains Mono","Cascadia Code",Consolas,monospace';
  const roundRect=(x0,y0,w,h,r)=>{ctx.beginPath();ctx.moveTo(x0+r,y0);ctx.arcTo(x0+w,y0,x0+w,y0+h,r);ctx.arcTo(x0+w,y0+h,x0,y0+h,r);ctx.arcTo(x0,y0+h,x0,y0,r);ctx.arcTo(x0,y0,x0+w,y0,r);ctx.closePath();};

  function paint(hover){
    ctx.clearRect(0,0,width,height);
    ctx.save();
    ctx.font='10px '+mono;ctx.textAlign='left';ctx.textBaseline='middle';
    for(let i=0;i<=4;i++){
      const value=low+(high-low)*i/4,yy=y(value);
      ctx.strokeStyle=i===0?'rgba(126,168,184,.22)':'rgba(126,168,184,.11)';
      ctx.lineWidth=1;ctx.setLineDash(i===0?[]:[2,5]);
      ctx.beginPath();ctx.moveTo(left,yy);ctx.lineTo(width-right,yy);ctx.stroke();
      ctx.fillStyle='rgba(154,175,187,.85)';ctx.fillText(number(value,0),0,yy);
    }
    ctx.setLineDash([]);

    const area=ctx.createLinearGradient(0,top,0,height-bottom);
    area.addColorStop(0,'rgba(46,230,176,.30)');
    area.addColorStop(.55,'rgba(46,230,176,.09)');
    area.addColorStop(1,'rgba(46,230,176,0)');
    ctx.beginPath();ctx.moveTo(x(0),y(points[0].equity));
    points.forEach((point,i)=>ctx.lineTo(x(i),y(point.equity)));
    ctx.lineTo(x(points.length-1),height-bottom);ctx.lineTo(x(0),height-bottom);ctx.closePath();
    ctx.fillStyle=area;ctx.fill();

    ctx.beginPath();ctx.strokeStyle='rgba(160,182,196,.55)';ctx.lineWidth=1.4;ctx.setLineDash([5,5]);
    points.forEach((point,i)=>i?ctx.lineTo(x(i),y(point.benchmark_equity)):ctx.moveTo(x(i),y(point.benchmark_equity)));
    ctx.stroke();ctx.setLineDash([]);

    const line=ctx.createLinearGradient(left,0,width-right,0);
    line.addColorStop(0,'#8ffcd0');line.addColorStop(.55,'#4fe0b0');line.addColorStop(1,'#7fd8ff');
    ctx.save();ctx.shadowColor='rgba(46,230,176,.55)';ctx.shadowBlur=16;
    ctx.beginPath();ctx.strokeStyle=line;ctx.lineWidth=2.2;ctx.lineJoin='round';ctx.lineCap='round';
    points.forEach((point,i)=>i?ctx.lineTo(x(i),y(point.equity)):ctx.moveTo(x(i),y(point.equity)));
    ctx.stroke();ctx.restore();

    const last=points[points.length-1];
    ctx.beginPath();ctx.fillStyle='rgba(46,230,176,.20)';ctx.arc(x(points.length-1),y(last.equity),8,0,Math.PI*2);ctx.fill();
    ctx.beginPath();ctx.fillStyle='#d8fff0';ctx.arc(x(points.length-1),y(last.equity),3.2,0,Math.PI*2);ctx.fill();

    ctx.fillStyle='rgba(154,175,187,.8)';ctx.textBaseline='alphabetic';
    ctx.textAlign='left';ctx.fillText(String(points[0].timestamp).slice(0,10),left,height-8);
    ctx.textAlign='right';ctx.fillText(String(last.timestamp).slice(0,10),width-right,height-8);

    if(Number.isInteger(hover)&&hover>=0&&hover<points.length){
      const hx=x(hover),point=points[hover];
      ctx.strokeStyle='rgba(200,255,232,.35)';ctx.lineWidth=1;ctx.setLineDash([3,4]);
      ctx.beginPath();ctx.moveTo(hx,top);ctx.lineTo(hx,height-bottom);ctx.stroke();ctx.setLineDash([]);
      for(const [key,color] of [['benchmark_equity','#a0b6c4'],['equity','#8ffcd0']]){
        ctx.beginPath();ctx.fillStyle=color;ctx.arc(hx,y(point[key]),3,0,Math.PI*2);ctx.fill();
      }
      const text=String(point.timestamp).slice(0,10)+'  |  '+number(point.equity,0);
      ctx.font='11px '+mono;
      const boxW=ctx.measureText(text).width+18;
      const boxX=Math.min(Math.max(left,hx-boxW/2),width-right-boxW);
      const boxY=Math.max(top+2,Math.min(y(point.equity)-40,height-bottom-28));
      ctx.fillStyle='rgba(9,16,23,.94)';ctx.strokeStyle='rgba(46,230,176,.42)';ctx.lineWidth=1;
      roundRect(boxX,boxY,boxW,24,8);ctx.fill();ctx.stroke();
      ctx.fillStyle='#d8fff0';ctx.textAlign='left';ctx.textBaseline='middle';ctx.fillText(text,boxX+9,boxY+12);
    }
    ctx.restore();
  }

  canvas._auroraChart={points,width,height,left,right,top,bottom,x,y};
  canvas._auroraPaint=paint;
  if(!canvas._auroraBound){
    canvas._auroraBound=true;
    canvas.addEventListener('pointermove',event=>{
      const geo=canvas._auroraChart;
      if(!geo||!canvas._auroraPaint)return;
      const box=canvas.getBoundingClientRect();
      if(!box.width)return;
      const px=(event.clientX-box.left)*(geo.width/box.width);
      let best=0,bestDelta=Infinity;
      for(let i=0;i<geo.points.length;i++){const delta=Math.abs(geo.x(i)-px);if(delta<bestDelta){bestDelta=delta;best=i;}}
      canvas._auroraPaint(best);
    });
    canvas.addEventListener('pointerleave',()=>{if(canvas._auroraPaint)canvas._auroraPaint(null);});
  }
  if(!canvas._auroraResize){
    canvas._auroraResize=true;let pending=null;
    window.addEventListener('resize',()=>{clearTimeout(pending);pending=setTimeout(()=>{try{drawChart();}catch{}},150);});
  }
  paint(null);
}
$('#research-form').addEventListener('submit',async event=>{event.preventDefault();const file=$('#data-file').files[0];if(!file)return;const button=$('#run-research');button.disabled=true;message('#research-message','Reading the file locally and checking it before any replay…');
  try{if(file.size>3_000_000)throw new Error('Choose a CSV smaller than 3 MB.');const stats=previewCsv(await file.text());pendingImportFile=file;renderCsvPreview(stats,file.name);$('#preview-apply').disabled=!stats.ok;message('#research-message',stats.ok?(practiceDataset?`Practice dataset generated in your browser${practiceSeed!==null?` · seed ${practiceSeed}`:''}. A flight simulator for the workflow — synthetic bars prove nothing about real markets. Read the preview, then apply.`:'The file checks out. Read the preview, then apply it to start the walk-forward evaluation.'):'The file has fixable problems — details below. Loki has not started a replay.',!stats.ok);}
  catch(error){pendingImportFile=null;$('#quant-csv-preview')&&($('#quant-csv-preview').hidden=true);message('#research-message',error.message,true);}
  finally{button.disabled=false;}
});
// PRACTICE DATASET — a flight simulator for the research workflow. The bars
// are built in this browser from a seeded random walk; they teach what a run,
// a preview, and a council review look like, and they prove nothing about
// real markets. They never earn the data-import step credit.
let practiceDataset=false,practiceSeed=null;
function generatePracticeDataset(){
  practiceSeed=(Date.now()%900001+Math.floor(Math.random()*8999))>>>0;
  let a=practiceSeed>>>0;const rnd=()=>{a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};
  const rows=['timestamp,open,high,low,close,volume'];let price=40000+rnd()*24000;
  const base=new Date();base.setUTCHours(0,0,0,0);base.setUTCDate(base.getUTCDate()-600);
  for(let i=0;i<600;i++){const drift=i%260<130?0.00045:-0.00025;const ret=drift+(rnd()-0.5)*0.036;const o=price,c=Math.max(1,o*(1+ret));const h=Math.max(o,c)*(1+rnd()*0.012),l=Math.min(o,c)*(1-rnd()*0.012);rows.push(base.toISOString().slice(0,10)+','+o.toFixed(2)+','+h.toFixed(2)+','+l.toFixed(2)+','+c.toFixed(2)+','+String(Math.round(300+rnd()*900)));price=c;base.setUTCDate(base.getUTCDate()+1);}
  const file=new File([rows.join('\n')],'synthetic-practice-btc.csv',{type:'text/csv'});const transfer=new DataTransfer();transfer.items.add(file);
  const input=$('#data-file');input.files=transfer.files;$('#asset-symbol').value='PRACTICE-BTC';practiceDataset=true;
  input.dispatchEvent(new Event('change',{bubbles:true}));
  $('#research-form').requestSubmit();
}
function previewCsv(text){const rows=csvRows(text.replace(/^\uFEFF/,''));const headers=(rows.shift()||[]).map(value=>value.toLowerCase());const required=['timestamp','open','high','low','close','volume'];
  if(required.some(key=>!headers.includes(key))||new Set(headers).size!==headers.length)throw new Error('Column problem: use unique CSV columns named timestamp, open, high, low, close, volume.');
  const duplicates=new Map(),invalid=[],dates=[];
  for(let i=0;i<rows.length;i++){const row=rows[i],bad=[];
    if(row.length!==headers.length)bad.push('wrong column count');
    for(const key of required){const raw=row[headers.indexOf(key)];if(!raw){bad.push(`${key} empty`);continue;}if(key!=='timestamp'){const value=Number(raw);if(!Number.isFinite(value))bad.push(`${key} not a number`);}}
    if(bad.length){if(invalid.length<3)invalid.push(`row ${i+2}: ${bad.join(' · ')}`);continue;}
    const ts=row[headers.indexOf('timestamp')];dates.push(ts);duplicates.set(ts,(duplicates.get(ts)||0)+1);}
  const duplicateRows=[...duplicates.values()].reduce((s,n)=>s+n-1,0);
  const dupeSamples=[...duplicates.entries()].filter(([,n])=>n>1).slice(0,3).map(([ts,n])=>`${ts.slice(0,10)} ×${n}`);
  const times=dates.map(Date.parse).filter(Number.isFinite).sort((a,b)=>a-b);
  let maxGap=0,gapCount=0;for(let i=1;i<times.length;i++){const gap=(times[i]-times[i-1])/86400000;if(gap>maxGap)maxGap=gap;if(gap>7)gapCount++;}
  const valid=dates.length;
  const range=times.length?`${new Date(times[0]).toISOString().slice(0,10)} → ${new Date(times.at(-1)).toISOString().slice(0,10)}`:'—';
  const ok=valid>=161&&valid<=5000&&invalid.length===0;
  return {ok,rows:rows.length,valid,range,maxGap,gapCount,duplicateRows,dupeSamples,invalidWin:invalid};
}
function renderCsvPreview(stats,name){const preview=$('#quant-csv-preview');if(!preview)return;preview.hidden=false;$('#preview-title').textContent=name;
  const host=$('#preview-metrics');host.replaceChildren();
  host.append(metricCard('Bars in file',number(stats.rows,0),'Rows after the header'));
  host.append(metricCard('Valid bars',number(stats.valid,0),stats.valid>=161&&stats.valid<=5000?'Within the 161–5,000 range':`Needs 161–5,000 usable bars (this file has ${number(stats.valid,0)})`));
  host.append(metricCard('Duplicates',number(stats.duplicateRows,0),stats.duplicateRows?`Same timestamp repeated — e.g. ${stats.dupeSamples.join(' · ')}`:'Every timestamp is unique'));
  host.append(metricCard('Invalid rows',number(stats.rows-stats.valid,0),stats.rows-stats.valid?`First problems: ${stats.invalidWin.join(' · ')||'bad columns or values'}`:'Nothing malformed found'));
  host.append(metricCard('Date range',stats.range,'Parsed from timestamps'));
  host.append(metricCard('Biggest gap',stats.maxGap?`${stats.maxGap.toFixed(1)} d`:'—',stats.gapCount?`${stats.gapCount} gap(s) over a week — weekends/holidays are normal`:'No multi-week holes'));
  const notes=[];if(stats.rows-stats.valid)notes.push('Loki will refuse to run until the malformed rows are cleaned out (invalid rows break the strict parser).');
  if(stats.duplicateRows)notes.push('Duplicate timestamps pass through as-is — the strategy uses each bar in file order.');
  notes.push('OHLCV files carry no currency column, so values are treated in the file’s quote currency — assumed USD unless your headline inputs say otherwise.');
  $('#preview-notes').textContent=notes.join(' ');}
async function applyImport(file){const button=$('#run-research');button.disabled=true;message('#research-message','Validating history and evaluating unseen windows…');
  try{const bars=parseBars(await file.text()),form=new FormData($('#research-form')),config=Object.fromEntries(['initial_capital','fee_bps','slippage_bps','periods_per_year'].map(key=>[key,Number(form.get(key))]));const symbol=String(form.get('symbol')).trim().toUpperCase();if(!symbol)throw new Error('Enter an asset or pair label.');const nextReport=await post('/api/research/evaluate',{bars,config});report=nextReport;reportTime=new Date().toISOString();currentBars=bars;currentConfig=config;currentSymbol=symbol;currentFile=file.name;datasetRevision++;quantResult=null;councilResult=null;$('#quant-results').hidden=true;$('#council-results').replaceChildren(element('div','Dataset changed. Convene the council to review this research.','empty-inline'));message('#council-message','');message('#quant-message','Research loaded. Run factor diagnostics and shadow replay on this history.');$('#paper-symbol').value=currentSymbol;renderReport();syncContext();message('#research-message',practiceDataset?'Practice run complete on synthetic bars. Use it to learn the workflow — the next honest step is a real dataset, then a fresh review.':'Research complete. The result is shared with Overview, the council, and Loki chat. Review costs and limitations below.');pendingImportFile=null;$('#quant-csv-preview')&&($('#quant-csv-preview').hidden=true);if(!practiceDataset)try{localStorage.setItem('loki_steps_data',JSON.stringify({at:Date.now()}))}catch(_e){}}
  catch(error){message('#research-message',`${error.message}${report?' Previous successful report remains displayed.':''}`,true);}finally{button.disabled=false;}
}
$('#preview-apply').addEventListener('click',()=>{if(pendingImportFile)applyImport(pendingImportFile);});
$('#preview-discard').addEventListener('click',()=>{$('#data-file').value='';$('#file-label').textContent='Choose historical OHLCV data';$('#quant-csv-preview').hidden=true;pendingImportFile=null;practiceDataset=false;practiceSeed=null;message('#research-message','');});
$('#download-report').addEventListener('click',()=>{if(report)exportJSON(report,`loki-research-${report.data_fingerprint.slice(0,12)}.json`);});

function renderQuant(){const {analysis,replay}=quantResult,target=$('#quant-results');target.replaceChildren();target.hidden=false;const summary=element('div',null,'quant-summary'),description=element('div');description.append(element('strong',analysis.signal.stance==='long_candidate'?'Historical long conditions present':'Cash / no long setup'),element('p',`${analysis.symbol} · ${analysis.observations} observations · score ${number(analysis.signal.score,3)} is descriptive, not a win probability`));summary.append(description,badge('Next open only',''));target.append(summary);const factors=element('div',null,'factor-grid');for(const factor of analysis.factors||[]){const card=element('article',null,'factor-card');const value=factor.unit==='fraction'||factor.unit==='return'?pct(factor.value):`${number(factor.value,4)}${factor.unit&&factor.unit!=='ratio'?' '+factor.unit:''}`;card.append(element('h3',factor.label),element('strong',value),element('p',factor.interpretation));factors.append(card);}target.append(factors);const checks=element('div',null,'check-list');for(const condition of analysis.signal.conditions||[])checks.append(checkRow(condition.name,condition.passed,`Observed ${number(condition.observed,4)} · threshold ${condition.threshold??'—'}`));target.append(checks,element('h3','Historical shadow replay','result-subheading'));const s=replay.summary;target.append(inlineMetrics([['Replay return',pct(s.total_return),'Full supplied history · not out-of-sample'],['Trade win rate',pct(s.win_rate),`${s.total_trades} closed trades`],['Maximum drawdown',pct(s.max_drawdown),`Benchmark ${pct(replay.benchmark?.total_return)}`]]));target.append(element('p',`Fees: ${number(s.total_fees)} · Slippage: ${number(s.total_slippage)} · Expectancy: ${number(s.expectancy)} per trade · 95% win-rate interval: ${s.win_rate_ci95?s.win_rate_ci95.map(pct).join('–'):'not estimable'}`,'caption'));target.append(element('h3','Replay cost sensitivity','result-subheading'),table(['Costs','Return','Drawdown','Win rate'],(replay.cost_stress||[]).map(s=>[`${s.cost_multiplier}×`,pct(s.total_return),pct(s.max_drawdown),pct(s.win_rate)])),bulletList([...new Set([...(analysis.limitations||[]),...(replay.limitations||[])])]),detailsJSON(quantResult));}
$('#run-quant').addEventListener('click',async()=>{if(!currentBars){message('#quant-message','Import and evaluate a dataset above first.',true);return;}const button=$('#run-quant'),revision=datasetRevision;button.disabled=true;message('#quant-message','Computing factors and replaying the paper strategy…');try{const result=await post('/api/fusion/quant',{bars:currentBars,symbol:currentSymbol,periods_per_year:currentConfig.periods_per_year,config:currentConfig});if(revision!==datasetRevision){message('#quant-message','Dataset changed during analysis. Run again for the current history.');return;}quantResult=result;renderQuant();message('#quant-message','Factor analysis and historical replay complete. Replay results are separate from the walk-forward test.');}catch(error){message('#quant-message',error.message,true);}finally{button.disabled=false;}});
function checkRow(name,passed,detail){const row=element('div',null,'check-row'+(passed?'':' failed')),body=element('div');body.append(element('strong',human(name)),element('p',detail));row.append(element('span',passed?'✓':'○','check-icon'),body);return row;}
$('#run-pullback').addEventListener('click',async()=>{
  if(!currentBars||currentBars.length<260){message('#pullback-message','Import at least 260 completed bars first.',true);return;}
  const button=$('#run-pullback'),revision=datasetRevision;button.disabled=true;
  message('#pullback-message','Selecting on training prices, then testing the frozen recipe…');
  try{
    const result=await post('/api/fusion/pullback',{bars:currentBars,symbol:currentSymbol,periods_per_year:currentConfig.periods_per_year,config:currentConfig});
    if(revision!==datasetRevision){message('#pullback-message','Dataset changed. Run the candidate test again.');return;}
    pullbackResult=result;pullbackDataRevision=revision;const summary=result.summary,target=$('#pullback-results');target.hidden=false;
    target.replaceChildren(inlineMetrics([['Later test return',pct(summary.total_return),'After estimated costs'],['Test win rate',pct(summary.win_rate),`${summary.total_trades} completed trades`],['Maximum drawdown',pct(summary.max_drawdown),'Initial equity included']]));
    target.append(element('p',`Selected recipe: ${Object.keys(result.parameters).length?JSON.stringify(result.parameters):'Cash / no eligible training candidate'} · 95% win-rate interval: ${summary.win_rate_ci95?summary.win_rate_ci95.map(pct).join('–'):'not estimable'}`,'caption'));
    target.append(table(['Cost multiplier','Test return','Expectancy'],result.cost_stress.map(row=>[`${row.multiplier}×`,pct(row.total_return),number(row.expectancy)])),bulletList(result.rejection_reasons),bulletList(result.assumptions),detailsJSON(result,'Inspect all training trials and test evidence'));
    message('#pullback-message','Candidate test complete. Fresh holdout provenance is unverified; this result does not prove 70% future wins.');
    try{localStorage.setItem('loki_steps_run',JSON.stringify({at:Date.now()}))}catch(_e){}
  }catch(error){message('#pullback-message',error.message,true);}finally{button.disabled=false;}
});
function portfolioContext(){if(!portfolio)return{};return {equity:portfolio.metrics?.equity,cash:portfolio.metrics?.cash??portfolio.state?.cash,positions:positionsArray().map(position=>({symbol:position.symbol,quantity:position.quantity,market_value:position.quantity*position.mark_price})),currency:portfolio.state?.quote_currency};}
function renderCouncil(){const result=councilResult,target=$('#council-results');target.replaceChildren();const decision=element('div',null,'council-decision'+(result.director.decision==='paper_proposal'?'':' wait'));decision.append(element('p','DIRECTOR / '+human(result.director.decision).toUpperCase(),'eyebrow'),element('h3',result.director.decision==='paper_proposal'?'A proposal to review on paper.':'Wait for a stronger case.'),element('p',result.director.summary));if(Array.isArray(result.director.blocked_by)&&result.director.blocked_by.length){const chips=element('div',null,'council-blocked');result.director.blocked_by.forEach(name=>chips.append(badge(name,'bad')));decision.append(chips);}target.append(decision);const analysts=element('div',null,'analyst-grid');for(const analyst of result.analysts||[]){const card=element('article',null,'analyst-card'),heading=element('div',null,'analyst-heading');heading.append(element('h3',analyst.title||human(analyst.role)),badge(analyst.status,analyst.status==='ready'?'good':analyst.status==='blocked'?'bad':'warning'));card.append(heading,element('p',analyst.summary));if(analyst.concerns?.length)card.append(bulletList(analyst.concerns));if(analyst.evidence&&Object.keys(analyst.evidence).length)card.append(detailsJSON(analyst.evidence,'Inspect supporting evidence'));analysts.append(card);}const unsure=(result.analysts||[]).filter(a=>a.status&&a.status!=='ready');if(unsure.length)analysts.append(element('p',`${unsure.map(a=>a.title||human(a.role)).join(', ')} did not clear this review — each card above holds their exact evidence and concerns, and the director weighed them before the decision.`,'council-disagree caption'));target.append(analysts,element('h3','Risk checks','result-subheading'));const checks=element('div',null,'check-list');for(const check of result.risk_checks||[])checks.append(checkRow(check.name,check.passed,check.detail));target.append(checks);if(result.proposal){const p=result.proposal,proposal=element('div',null,'proposal-card');proposal.append(element('h3',`${p.symbol} · ${p.blocked_by?.length?'blocked sizing draft':'paper proposal only'}`),inlineMetrics([['Reference entry',number(p.entry_reference,8)],['Quantity',number(p.quantity,8)],['Reference stop',number(p.stop_reference,8)]]),element('p',`Planned stop loss: ${number(p.planned_loss_at_stop)} · Cash required: ${number(p.cash_required)} · Reward / risk after costs: ${number(p.reward_risk_after_costs)}`,'caption'));if(p.blocked_by?.length)proposal.append(element('p','Blocked by: '+p.blocked_by.join('; ')+'. This draft has not passed the council checks.','caption'));const button=element('button',p.blocked_by?.length?'Inspect draft in paper form →':'Review in paper journal →','button secondary');button.type='button';button.addEventListener('click',()=>{prefillPaper({symbol:p.symbol,price:p.entry_reference,quantity:p.quantity,stop_loss:p.stop_reference});location.hash='portfolio';toast('Proposal copied to the paper form. Review the values before recording.');});proposal.append(button);target.append(proposal);}const targetInfo=result.performance_target||{};target.append(element('div',`70% trade-win target · observed ${pct(targetInfo.observed_win_rate)} · 95% lower bound ${pct(targetInfo.lower_confidence_bound)} · ${targetInfo.supported?'historically supported by this report':'not statistically supported by this evidence'}. Future performance is not guaranteed.`,'council-target'),bulletList(result.limitations),detailsJSON(result,'Inspect complete council review'));}
function renderEvidenceStrip(){const target=$('#live-evidence-strip');if(!target)return;if(!liveEvidence){target.replaceChildren();return;}const strip=element('div',null,'metrics');const newsOk=liveEvidence.news?.status==='ok',techOk=liveEvidence.technical?.status==='ok',fundOk=liveEvidence.fundamentals?.status==='ok';strip.append(metricCard('Public bars',`${liveEvidence.bars.length} × 5m`,`From ${liveEvidence.bars_source}`),metricCard('News lexicon',newsOk?String(liveEvidence.news.score):'abstained',newsOk?`${liveEvidence.news.headlines_read} public headlines, open word weights`:'No usable headlines — named, not guessed'),metricCard('Technicals',techOk?String(liveEvidence.technical.score):'abstained',techOk?`last ${liveEvidence.technical.facts.last} · SMA25 ${liveEvidence.technical.facts.sma25} · RSI ${liveEvidence.technical.facts.rsi14}`:'Bars arrived, averages did not compute'),metricCard('Fundamentals',fundOk?String(liveEvidence.fundamentals.score):'abstained',fundOk?(liveEvidence.fundamentals.verdict||'banded'):(liveEvidence.fundamentals?.reason||'no usable read')));target.replaceChildren(strip);}
async function runLiveEvidence(){const button=$('#live-evidence-run'),symbol=($('#live-evidence-symbol').value||'').trim().toUpperCase();if(!symbol){message('#live-evidence-message','Type a symbol first — live evidence rides on it.',true);return;}button.disabled=true;message('#live-evidence-message','Reading public bars and the desk agents in one fetch, so the council and the desk quote the same numbers…');try{const evidence=await request('/api/desk/evidence',{symbol});if(evidence.status&&evidence.status!=='ok'){liveEvidence=null;renderEvidenceStrip();message('#live-evidence-message',evidence.error||evidence.note||'The public feeds answered nothing usable; nothing will be invented.',true);return;}liveEvidence=evidence;renderEvidenceStrip();$('#council-context').textContent=`${evidence.symbol} · live public evidence`;$('#council-context-detail').textContent=`${evidence.bars.length} five-minute bars cached from ${evidence.bars_source}; the desk agents quoted this same fetch above.`;message('#live-evidence-message','Live evidence cached — convene the council to review it. The imported-dataset path stays untouched.');}catch(error){message('#live-evidence-message',error.message,true);}finally{button.disabled=false;}}
$('#live-evidence-run').addEventListener('click',runLiveEvidence);
renderCouncilHistory('#council-history');
$('#council-history-clear').addEventListener('click',clearCouncilHistory);
$('#run-council').addEventListener('click',async()=>{const liveView=!!liveEvidence&&!currentBars;if(!currentBars&&!liveView){message('#council-message','Import and evaluate a dataset in Quant lab first, or fetch live evidence above.',true);return;}if(liveView&&$('#miro-native-id').value.trim()){message('#council-message','The native MiroFish report is bound to imported dataset scenarios. Leave that field empty for a live-bars review — this side of the panel does not replay it.',true);return;}const button=$('#run-council'),revision=datasetRevision,paperRevision=portfolioRevision;button.disabled=true;message('#council-message','Research, signal, risk, and execution reviewers are checking the shared evidence…');try{const answer=await (liveView?(()=>{const body={bars:liveEvidence.bars,symbol:liveEvidence.symbol,portfolio:portfolioContext(),config:{periods_per_year:liveEvidence.periods_per_year}};const news=newsPacket(liveEvidence.news);if(news)body.news_evidence=news;return request('/api/fusion/council',body);})():post('/api/fusion/council',{bars:currentBars,symbol:currentSymbol,portfolio:portfolioContext(),research:report,config:currentConfig||{}}));if(revision!==datasetRevision||paperRevision!==portfolioRevision){message('#council-message','Research or paper portfolio changed during review. Convene the council again.');return;}councilResult=answer;renderCouncil();pushCouncilHistory({symbol:answer.symbol,decision:answer.director&&answer.director.decision||'wait',blocked:(answer.director&&Array.isArray(answer.director.blocked_by)?answer.director.blocked_by.length:0),source:liveView?'overview':'dataset'});renderCouncilHistory('#council-history');message('#council-message',`Review complete · ${answer.engine==='deterministic_role_pipeline'?'local rules-based role pipeline':human(answer.engine)} · evidence as of ${answer.as_of}${liveView?' · live public evidence':''}${liveView&&newsPacket(liveEvidence.news)?' · desk news read attached as bounded context':''}`);try{localStorage.setItem('loki_steps_council',JSON.stringify({at:Date.now()}))}catch(_e){}}catch(error){message('#council-message',error.message,true);}finally{button.disabled=false;}});

function positionsArray(){const positions=portfolio?.state?.positions||[];return Array.isArray(positions)?positions:Object.entries(positions).map(([symbol,value])=>({...value,symbol:value.symbol||symbol}));}
function metricCard(label,value,note){const card=element('article',null,'metric');card.append(element('p',label),element('strong',value),element('small',note));return card;}
/* Display currency follows the shared switcher (AUD/USD). The paper ledger is
   always stored in USD; this only changes what is shown, never the math. */
function displayMoney(usdValue){const shared=window.LokiCurrency;if(shared&&typeof shared.format==='function')return shared.format(usdValue);return`US$${number(usdValue)}`;}
document.addEventListener('loki:currency',()=>{if(portfolio)renderPortfolio();});
function savePortfolio(){try{localStorage.setItem(storageKey,JSON.stringify(portfolio.state));$('#portfolio-storage').textContent=`Saved in this browser · ${portfolio.state.quote_currency} · fee ${portfolio.state.fee_bps} bps + slippage ${portfolio.state.slippage_bps} bps per side. Manual prices are not live data.`;}catch{$('#portfolio-storage').textContent='Browser storage is unavailable. The paper journal is held in this tab only; export it before closing.';}}
function renderPortfolio(){const m=portfolio.metrics||{},s=portfolio.state||{},positions=positionsArray();$('#portfolio-metrics').replaceChildren(metricCard('Paper equity',displayMoney(m.equity??m.total_equity),`Ledger cash US$${number(m.cash??s.cash)} in ${s.quote_currency||'USD'} · manual marks`),metricCard('Paper return',pctPoints(m.total_return_pct),`Initial capital US$${number(s.initial_capital)} in the ledger`),metricCard('Open exposure',pctPoints(m.gross_exposure_pct),`${positions.length} open position${positions.length===1?'':'s'}`),metricCard('Realized paper P&L',displayMoney(m.realized_pnl??s.realized_pnl),`Unrealized ${displayMoney(m.unrealized_pnl)} · after costs`));
  if(!positions.length)$('#portfolio-positions').replaceChildren(element('div','No open paper positions. Record an entry below or review a council proposal.','empty-inline'));else{
    const rows=positions.map(p=>{const actions=element('div',null,'row-actions');for(const[action,label]of[['mark','Mark'],['sell','Sell']]){const button=element('button',label,'row-action');button.type='button';button.addEventListener('click',()=>{prefillPaper({action,symbol:p.symbol,price:p.current_price??p.mark_price??p.last_price??p.average_price??p.entry_price,quantity:p.quantity});$('#portfolio-form').scrollIntoView({block:'center'});$('#portfolio-form [name="price"]').focus();});actions.append(button);}
      const markTime=p.mark_updated_at?` · ${new Date(p.mark_updated_at).toLocaleString([],{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})} · ${p.mark_source||'manual'}`:' · time not recorded (older journal)';
      const openedAt=p.opened_at?` · opened ${new Date(p.opened_at).toLocaleString([],{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})}`:'';
      return[p.symbol,number(p.quantity,8),displayMoney(p.average_price??p.average_entry??p.entry_price??p.avg_cost)+openedAt,displayMoney(p.current_price??p.mark_price??p.last_price)+markTime,displayMoney(p.quantity*p.mark_price),displayMoney(p.quantity*(p.mark_price-p.average_price)-p.entry_fees),actions];});$('#portfolio-positions').replaceChildren(table(['Asset','Quantity','Average entry','Manually set mark','Market value','Unrealized P&L','Actions'],rows));
  }
  const ledger=s.ledger||s.trades||s.transactions||[];const researchLink=(fp)=>{if(!fp)return'—';if(report&&report.data_fingerprint===fp){const anchor=element('a','this run ↗','research-link');anchor.href='#strategy-lab';return anchor;}return`run ${String(fp).slice(0,10)}…`;};
  $('#portfolio-ledger').replaceChildren(ledger.length?table(['Action','Asset','Quantity','Price','Fees / costs','Recorded','Research link'],[...ledger].reverse().slice(0,100).map(item=>[human(item.action||item.side||item.type),item.symbol,number(item.quantity,8),displayMoney(item.price),displayMoney(item.fee??item.fees??item.costs),String(item.timestamp||item.recorded_at||item.as_of||'—'),researchLink(item.report_fingerprint)])):element('p','No paper activity recorded yet.','caption'));savePortfolio();
}
async function updatePortfolio(payload={action:'snapshot'}){if(portfolioBusy)throw new Error('A paper journal update is already running.');portfolioBusy=true;try{const result=await post('/api/fusion/portfolio',{...payload,state:payload.action==='reset'?null:portfolio?.state||null});portfolio=result;portfolioRevision++;renderPortfolio();if(payload.action!=='snapshot'){if(councilResult){councilResult=null;$('#council-results').replaceChildren(element('div','The paper portfolio changed. Convene the council again for current risk checks.','empty-inline'));message('#council-message','Previous review cleared because the paper portfolio changed.');}if(scenarioResult){scenarioResult=null;$('#scenario-results').hidden=true;$('#scenario-results').replaceChildren();message('#scenario-message','Previous stress result cleared because the paper portfolio changed. Run it again for current positions.');}}return result;}finally{portfolioBusy=false;}}
async function loadPortfolio(){try{let stored=null;try{const raw=localStorage.getItem(storageKey);if(raw)stored=JSON.parse(raw);}catch{}if(stored){portfolio={state:stored,metrics:{}};await updatePortfolio();}else{portfolio=await request('/api/fusion/portfolio');renderPortfolio();}message('#portfolio-message','');}catch(error){message('#portfolio-message',`The saved paper journal could not be loaded: ${error.message} Export the workspace to preserve it, or reset the local journal.`,true);$('#portfolio-metrics').replaceChildren(metricCard('Paper journal unavailable','—','Refresh or reset after reviewing the error.'));}}
function updatePaperAction(){const action=$('#portfolio-form [name="action"]').value,isMark=action==='mark';$('#quantity-label').hidden=isMark;$('#portfolio-form [name="quantity"]').required=!isMark;$('#paper-stop-label').hidden=action!=='buy';}
function prefillPaper(values){for(const[key,value]of Object.entries(values)){const input=$(`#portfolio-form [name="${key}"]`);if(input&&value!=null)input.value=value;}if(!values.action)$('#portfolio-form [name="action"]').value='buy';updatePaperAction();}
$('#portfolio-form [name="action"]').addEventListener('change',updatePaperAction);
$('#portfolio-form').addEventListener('submit',async event=>{event.preventDefault();const form=new FormData(event.target),action=String(form.get('action')),payload={action,symbol:String(form.get('symbol')).trim().toUpperCase(),price:Number(form.get('price'))};if(action!=='mark')payload.quantity=Number(form.get('quantity'));else{payload.marks={[payload.symbol]:payload.price};delete payload.symbol;delete payload.price;}if(action==='buy'&&form.get('stop_loss'))payload.stop_loss=Number(form.get('stop_loss'));if(report)payload.report_fingerprint=report.data_fingerprint;const button=event.target.querySelector('[type="submit"]');button.disabled=true;message('#portfolio-message','Recording paper action…');try{await updatePortfolio(payload);message('#portfolio-message',`${human(action)} recorded in the local paper journal.${action==='buy'&&report?` It is tagged to the research fingerprint ${report.data_fingerprint.slice(0,12)}… so the journal and later reviews can trace this entry to the run that motivated it.`:''} No broker order was sent.`);toast('Paper journal updated.');}catch(error){message('#portfolio-message',error.message,true);}finally{button.disabled=false;}});
$('#reset-portfolio-form').addEventListener('submit',async event=>{event.preventDefault();const button=event.target.querySelector('button');button.disabled=true;try{await updatePortfolio({action:'reset',...Object.fromEntries([...new FormData(event.target)].map(([key,value])=>[key,key==='quote_currency'?String(value).trim().toUpperCase():Number(value)]))});message('#portfolio-message','A new local paper journal is ready.');}catch(error){message('#portfolio-message',error.message,true);}finally{button.disabled=false;}});
$('#refresh-portfolio').addEventListener('click',async event=>{event.target.disabled=true;try{await updatePortfolio();message('#portfolio-message','Snapshot refreshed using recorded manual marks.');}catch(error){message('#portfolio-message',error.message,true);}finally{event.target.disabled=false;}});
$('#use-last-close').addEventListener('click',()=>{if(!currentBars){toast('Import history in Quant lab first.');return;}prefillPaper({symbol:currentSymbol,price:currentBars.at(-1).close});toast(`Last historical close copied (${currentBars.at(-1).timestamp}). This is not a live price.`);});
for(const selector of ['#export-workspace','#export-context'])$(selector).addEventListener('click',exportWorkspace);
$('#risk-form').addEventListener('input',()=>{riskRevision++;sizing=null;$('#use-sizing').disabled=true;$('#risk-result').textContent='Inputs changed. Calculate again to refresh the preview.';});
$('#risk-form').addEventListener('submit',async event=>{event.preventDefault();sizing=null;$('#use-sizing').disabled=true;const revision=riskRevision,button=event.target.querySelector('[type="submit"]');button.disabled=true;try{const result=await post('/api/risk/preview',numericForm(event.target));if(revision!==riskRevision)return;sizing=result;$('#risk-result').textContent=`Quantity: ${number(sizing.quantity,8)} units\nCash required: ${number(sizing.cash_required)}\nPlanned loss at stop: ${number(sizing.planned_loss_at_stop)} / ${number(sizing.risk_budget)} budget\nBinding limit: ${sizing.binding_limit}. Preview only; no order submitted.`;$('#use-sizing').disabled=false;}catch(error){if(revision===riskRevision)$('#risk-result').textContent=error.message;}finally{button.disabled=false;}});
$('#use-sizing').addEventListener('click',()=>{if(!sizing)return;const form=new FormData($('#risk-form'));prefillPaper({symbol:currentSymbol||$('#paper-symbol').value,price:form.get('entry'),quantity:sizing.quantity,stop_loss:form.get('stop')});$('#portfolio-form').scrollIntoView({block:'center'});toast('Position preview copied. Review the paper entry before recording.');});

$('#scenario-compare').addEventListener('click',async()=>{if(!portfolio){message('#scenario-message','Load or reset the paper journal first, then run the comparison.',true);return;}
  const form=new FormData($('#scenario-form')),multiplier=Number(form.get('volatility_multiplier')),shocks=[-15,-10,-5,-2.5,2.5,5];
  const button=$('#scenario-compare'),revision=portfolioRevision;button.disabled=true;message('#scenario-message','Running the same stress at several shock sizes…');
  try{const rows=[];
    for(const shock of shocks){if(revision!==portfolioRevision)throw new Error('Paper portfolio changed during the comparison. Run the comparison again.');rows.push({shock,...await post('/api/fusion/scenario',{portfolio:portfolio.state,shock_pct:shock,volatility_multiplier:multiplier})});}
    if(revision!==portfolioRevision)throw new Error('Paper portfolio changed during the comparison. Run the comparison again.');
    const worst=rows.reduce((a,b)=>Math.abs(b.pnl)>Math.abs(a.pnl)?b:a);
    $('#scenario-results').hidden=false;
    $('#scenario-compare-out').replaceChildren(
      table(['Shock','Stressed equity','P&L','Return'],rows.map(row=>[`${row.shock>0?'+':''}${row.shock}%`,number(row.stressed_equity),number(row.pnl),pctSigned(row.return_pct)])),
      element('p',`Every row uses your same positions and marks, the ${multiplier}× volatility multiplier and the account's own fees and slippage. Largest swing: ${worst.shock>0?'+':''}${worst.shock}% (${number(worst.pnl)}). The table compares shock size only — it never estimates how likely each shock is.`,'caption'));
    message('#scenario-message','Shock comparison complete — read the side-by-side table below.');
  }catch(error){message('#scenario-message',error.message,true);}finally{button.disabled=false;}});
$('#scenario-form').addEventListener('submit',async event=>{event.preventDefault();if(!portfolio){message('#scenario-message','Load or reset the paper journal first.',true);return;}const revision=portfolioRevision,button=event.target.querySelector('button');button.disabled=true;message('#scenario-message','Applying the shock to current paper marks…');try{const result=await post('/api/fusion/scenario',{portfolio:portfolio.state,...numericForm(event.target)});if(revision!==portfolioRevision){message('#scenario-message','Paper portfolio changed during this calculation. Run again for current positions.');return;}scenarioResult=result;const target=$('#scenario-results');target.hidden=false;target.replaceChildren(inlineMetrics([['Baseline equity',number(result.baseline_equity)],['Stressed equity',number(result.stressed_equity)],['Stress P&L',number(result.pnl),pctPoints(result.return_pct)]]));if(result.positions?.length)target.append(table(['Asset','Current mark','Stressed price','P&L'],result.positions.map(p=>[p.symbol,number(p.current_price,8),number(p.stressed_price,8),number(p.pnl)])));else target.append(element('p','The paper journal has no open positions, so the price shock leaves cash unchanged.','caption'));target.append(bulletList(result.assumptions),detailsJSON(result));message('#scenario-message','Stress calculation complete. This is a sensitivity scenario, not a forecast.');}catch(error){message('#scenario-message',error.message,true);}finally{button.disabled=false;}});

function componentStatus(component){const raw=component.status||component.state||'unknown';return{raw,label:human(raw),tone:['ready','active','available','configured','integrated','local'].includes(raw)?'good':['disabled','unavailable','license_required','blocked'].includes(raw)?'warning':''};}
function renderCapabilities(){const target=$('#integration-cards');target.replaceChildren();const components=capabilities.components||[];for(const component of components){const status=componentStatus(component),card=element('article',null,'integration-card');card.append(element('div',String(component.name||component.id||'?').slice(0,1),'component-mark'));const heading=element('div',null,'section-title');heading.append(element('h2',component.name||human(component.id)),badge(status.label,status.tone));card.append(heading,element('p',component.reason||component.message||'See component capabilities below.'));const list=element('div',null,'capability-list');for(const cap of component.capabilities||[])list.append(element('span',human(typeof cap==='string'?cap:cap.name||cap.id)));card.append(list,element('p',typeof component.license==='string'?`Source license: ${component.license}`:component.license?`Source license: ${JSON.stringify(component.license)}`:'Source licensing is documented with the integration.','integration-license'));const linkTarget=/miro/i.test(component.id)?'scenarios':/fincept/i.test(component.id)?'fincept-panel':/hedge|council/i.test(component.id)?'agent-council':'strategy-lab';const link=element('a','Open workspace tool →','text-link');link.href=linkTarget==='fincept-panel'?'#integrations':`#${linkTarget}`;if(linkTarget==='fincept-panel')link.addEventListener('click',()=>$('#fincept-panel').scrollIntoView({block:'start'}));card.append(link);target.append(card);}$('#integration-summary').textContent=`${components.length} components · ${human(capabilities.mode||'paper research')} · ${capabilities.local_actions_enabled?'local external actions enabled':'external actions disabled in this session'}`;}
async function loadCapabilities(){const button=$('#refresh-integrations');button.disabled=true;message('#integration-message','');try{capabilities=await request('/api/fusion/capabilities');renderCapabilities();}catch(error){message('#integration-message',`Could not read integration availability. ${error.message}`,true);$('#integration-summary').textContent='Component status unavailable.';}finally{button.disabled=false;}await Promise.allSettled([loadNarrativeStatus(),loadFinceptStatus()]);}
$('#refresh-integrations').addEventListener('click',loadCapabilities);
async function loadNarrativeStatus(){
  const local=Boolean(capabilities?.local_actions_enabled);
  $('#narrative-status').textContent=local?'Local engine ready':'Engine ready · reports save only with the local launcher';
  const saveBox=$('#narrative-form [name="save"]');
  if(saveBox){saveBox.disabled=!local;if(!local)saveBox.checked=false;}
}
function renderNarrative(data){
  const target=$('#narrative-results');target.hidden=false;target.replaceChildren();
  target.append(element('p',`Aggregate stance ${data.lean} · ${String(data.aggregate_stance)} of [-100, +100]`,'narrative-lean'));
  const traj=element('div',null,'narrative-trajectory');
  traj.append(element('p','STANCE TRAJECTORY','eyebrow'));
  for(const item of (data.trajectory||[]))traj.append(element('p',`Round ${item.round}: ${item.stance} · bullish ${item.shares.bullish}% / neutral ${item.shares.neutral}% / bearish ${item.shares.bearish}%`,'narrative-round'));
  target.append(traj);
  const agents=element('div',null,'narrative-agents');
  agents.append(element('p','PERSONA FAMILIES AT THE FINAL ROUND','eyebrow'));
  const byFamily={};
  for(const agent of (data.agents||[]))(byFamily[agent.family]=byFamily[agent.family]||[]).push(Number(agent.stance));
  for(const family of Object.keys(byFamily)){const stances=byFamily[family];const mean=stances.reduce((a,b)=>a+b,0)/stances.length;agents.append(element('p',`${family} · final ${mean.toFixed(1)}`,'narrative-agent'));}
  target.append(agents);
  const eventsBlock=element('div',null,'narrative-events');
  eventsBlock.append(element('p','PARSED STANCE EVENTS'+(Number(data.events_skipped)?` · ${data.events_skipped} sentence(s) skipped (no directional language)`:''),'eyebrow'));
  if(!(data.events||[]).length)eventsBlock.append(element('p','No directional sentences were parsed — nothing was invented to fill the gap.','integration-note'));
  for(const event of (data.events||[]).slice(0,12))eventsBlock.append(element('p',`${event.direction>0?'+':'−'}${event.hedged?' (hedged)':''} ${event.text}${event.tickers&&event.tickers.length?' ['+event.tickers.join(', ')+']':''}`,'narrative-event'));
  target.append(eventsBlock);
  if(data.saved&&data.saved.report_id){
    const row=element('p',null,'narrative-saved');
    row.append(element('span',`Saved as native report ${data.saved.report_id}. `,'caption'));
    const send=document.createElement('button');send.type='button';send.className='button secondary';send.textContent='Send to the Defence Council →';
    send.addEventListener('click',()=>{
      $('#miro-native-id').value=data.saved.report_id;
      const review=$('#miro-native-reviewed');if(review)review.checked=false;
      location.hash='#agent-council';
      message('#council-message','The native narrative report id is filled in. Read the report, then tick the reviewed confirmation yourself.');
    });
    row.append(send);target.append(row);
  }
  target.append(detailsJSON(data,'Inspect full simulation result'));
  target.append(element('p','Deterministic text statistics — not a forecast, not a probability, and not verified trading evidence.','caption'));
}
$('#narrative-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const form=new FormData(event.target);
  const seedText=String(form.get('seed_text')||'').trim();
  if(!seedText)message('#narrative-message','Paste source material for the simulation to read.',true);
  const payload={seed_text:seedText,rounds:Number(form.get('rounds'))||6,save:form.get('save')!==null};
  const question=String(form.get('question')||'').trim();if(question)payload.question=question;
  const title=String(form.get('title')||'').trim();if(title)payload.title=title;
  const button=event.target.querySelector('[type="submit"]');
  if(!seedText)return;
  button.disabled=true;
  message('#narrative-message','Running the deterministic local simulation…');
  try{renderNarrative(await request('/api/fusion/narrative',payload,true));message('#narrative-message','Simulation complete. Every stance movement traces back to the parsed events above.');}
  catch(error){message('#narrative-message',error.message,true);}
  finally{button.disabled=false;}
});
async function miroNativeLibrary(){
  const button=$('#miro-native-library');
  if(!button)return;
  button.disabled=true;
  message('#miro-native-library-message','Reading saved reports from the local launcher…');
  try{
    const result=await request('/api/fusion/native-mirofish/reports',undefined,true),rows=Array.isArray(result.reports)?result.reports:[],target=$('#miro-native-library-list');
    if(!rows.length){target.replaceChildren(element('p','No saved narrative reports in the local launcher data yet — run one in Scenarios with save ticked.','caption'));message('#miro-native-library-message','');return;}
    target.replaceChildren(...rows.map(row=>{
      const rowNode=element('p',null,'native-report-row');
      const use=element('button','Use →','button secondary');
      use.type='button';
      if(row.unreadable){rowNode.append(element('strong',row.report_id),element('span',' · unreadable local artifact — kept visible, no fields invented for it','caption'));use.disabled=true;}
      else{
        rowNode.append(element('strong',row.title||'Untitled simulation'));
        rowNode.append(element('span',` · ${row.created_at?String(row.created_at).slice(0,19).replace('T',' '):'creation time not recorded'} · ${row.status||'status not recorded'} · ${row.report_id}`,'caption'));
      }
      use.addEventListener('click',()=>{
        $('#miro-native-id').value=row.report_id;
        $('#miro-native-reviewed').checked=false;
        $('#miro-native-preview').replaceChildren();
        message('#miro-native-message',`Loaded ${row.report_id} from the saved reports. Inspect it, then tick the reviewed confirmation yourself.`);
        $('#miro-native-id').focus();
      });
      rowNode.append(use);
      return rowNode;
    }));
    message('#miro-native-library-message',`Listed ${rows.length} saved report${rows.length===1?'':'s'} from the launcher's local data — newest first, echo of what was saved.`);
  }catch(error){message('#miro-native-library-message',error.message,true);}
  finally{button.disabled=false;}
}
$('#miro-native-library').addEventListener('click',miroNativeLibrary);
async function loadFinceptStatus(){try{finceptStatus=capabilities?.local_actions_enabled?await request('/api/fusion/fincept/status',undefined,true):(capabilities?.components||[]).find(item=>item.id==='fincept');if(!finceptStatus)throw new Error('Integration status is unavailable.');$('#fincept-status').textContent=human(finceptStatus.state||finceptStatus.status);$('#fincept-availability').textContent=finceptStatus.message||'The private engine reports its current configuration here.';$('#run-fincept').disabled=!(finceptStatus.configured&&(finceptStatus.licensed||finceptStatus.license_confirmed)&&(finceptStatus.jobs_enabled||finceptStatus.jobs_allowed)&&capabilities?.local_actions_enabled);}catch(error){$('#fincept-status').textContent='Unavailable';$('#fincept-availability').textContent=error.message;$('#run-fincept').disabled=true;}}
$('#fincept-form').addEventListener('submit',async event=>{event.preventDefault();if(!currentBars){message('#fincept-message','Import history in Quant lab first.',true);return;}if($('#fincept-frequency').value!=='daily'){message('#fincept-message','This risk workflow requires daily observations. Import daily history and confirm the frequency.',true);return;}const intervals=currentBars.slice(1).map((bar,index)=>(Date.parse(bar.timestamp)-Date.parse(currentBars[index].timestamp))/86400000).sort((a,b)=>a-b);const medianInterval=intervals[Math.floor(intervals.length/2)];if(!Number.isFinite(medianInterval)||medianInterval<.9||medianInterval>4.1){message('#fincept-message','The timestamp spacing does not look daily. Fincept expects daily observations (including business-day gaps); import daily history before using its 252-day annualization.',true);return;}const returns=currentBars.slice(1).map((bar,index)=>bar.close/currentBars[index].close-1);if(returns.length>2000){message('#fincept-message','Use a dataset with at most 2,001 daily bars (2,000 returns) for Fincept analytics.',true);return;}const button=$('#run-fincept'),revision=datasetRevision;button.disabled=true;message('#fincept-message','Running the licensed local Fincept risk engine…');try{const result=await request('/api/fusion/fincept/analyze',{returns:[returns],weights:[1],portfolio_value:Number(new FormData(event.target).get('portfolio_value')),confidence:.95},true);if(revision!==datasetRevision){message('#fincept-message','Dataset changed during analysis. Run again for the current history.');return;}const data=result.data||result,risk=data.basic_risk_metrics||{},valueAtRisk=data.var_analysis?.var_95?.historical||{},target=$('#fincept-results');target.hidden=false;target.replaceChildren(inlineMetrics([['Annualized volatility',pct(risk.volatility_annual),'252-day annualization'],['Historical 95% VaR',pct(valueAtRisk.var),'Daily return estimate'],['Maximum drawdown',pct(risk.max_drawdown?.max_drawdown??risk.max_drawdown),'Supplied daily history']]),detailsJSON(result,'Inspect Fincept risk, stress, and decomposition'));message('#fincept-message','Fincept risk analysis complete. Full results include model assumptions and stress estimates.');}catch(error){message('#fincept-message',error.message,true);}finally{button.disabled=!(finceptStatus?.configured&&capabilities?.local_actions_enabled);}});

function addChat(text,role,links){const div=element('div',null,`chat-message ${role}`);div.append(element('span',role==='user'?'YOU':'LOKI'),element('p',text));if(role==='assistant'&&links&&links.length){const row=element('p',null,'chat-context-row');const lead=element('span','EVIDENCE: ','chat-evidence-label');row.append(lead);for(const link of links){const a=document.createElement('a');a.textContent=link[0];a.href=link[1];a.className='text-link';row.append(a);}div.append(row);}const log=$('#chat-messages');log.append(div);while(log.children.length>40)log.firstElementChild.remove();log.scrollTop=log.scrollHeight;}
async function sendChat(text){const button=$('#chat-form button'),input=$('#chat-input');if(button.disabled)return;button.disabled=true;input.disabled=true;addChat(text,'user');input.value='';try{const context={data_mode:report?'uploaded historical CSV (unverified)':'no dataset supplied',trading_mode:'paper research only',as_of:reportTime||'no research run yet',previous_intent:previousIntent,conversation:previousConversation,symbol:currentSymbol||null,portfolio:portfolioContext(),metrics:portfolio?.metrics||{},positions:positionsArray(),recent_trades:portfolio?.state?.trades?.slice(-30)||[],current_prices:Object.fromEntries(positionsArray().map(p=>[p.symbol,p.mark_price]))};if(report){context.latest_backtest=report;context.strategy=report.strategy;}if(sizing)context.position_preview=sizing;if(councilResult)context.council=councilResult;if(quantResult)context.factor_analysis=quantResult.analysis;if(scenarioResult)context.scenario=scenarioResult;const reply=await post('/api/copilot',{message:text,context});previousIntent=reply.intent;previousConversation=reply.conversation||null;addChat(reply.text,'assistant',(()=>{const links=[];if(report)links.push(['Quant lab result →','#strategy-lab']);if(councilResult)links.push(['Council review →','#agent-council']);if(positionsArray().length||portfolio?.state?.trades?.length)links.push(['Paper journal →','#portfolio']);return links;})());const prompts=$('#chat-prompts');prompts.replaceChildren();for(const suggestion of(reply.suggestions||[]).slice(0,3)){const b=element('button',suggestion);b.type='button';b.dataset.prompt=suggestion;prompts.append(b);}}catch(error){addChat(`I couldn't complete that request. ${error.message}`,'assistant');}finally{button.disabled=false;input.disabled=false;input.focus();}}
$('#chat-form').addEventListener('submit',event=>{event.preventDefault();const text=$('#chat-input').value.trim();if(text)sendChat(text);});
$('#chat-prompts').addEventListener('click',event=>{const button=event.target.closest('[data-prompt]');if(button)sendChat(button.dataset.prompt);});
$$('[data-ask]').forEach(link=>link.addEventListener('click',()=>{sendChat(link.dataset.ask);}));
new ResizeObserver(drawChart).observe($('#equity-chart'));
updatePaperAction();syncContext();navigate();Promise.allSettled([loadPortfolio(),loadCapabilities()]);

// PINNED RESEARCH RUNS — evidence an honest terminal keeps between sessions.
// A pin snapshots a finished report: its fingerprint, windows, costs and
// verdict. Comparing a pin to the current run is arithmetic on saved
// evidence only. The change column describes those two runs better/worse
// per metric — it never predicts the market.
const PIN_KEY='loki_pinned_report_v1';
function readPin(){try{const raw=localStorage.getItem(PIN_KEY);if(!raw)return null;const parsed=JSON.parse(raw);return parsed&&parsed.report&&parsed.fingerprint?parsed:null;}catch(_e){return null;}}
function writePin(){if(!report)return;try{localStorage.setItem(PIN_KEY,JSON.stringify({fingerprint:report.data_fingerprint,symbol:currentSymbol||'dataset',pinned_at:new Date().toISOString(),report}));toast('Run pinned. Compare it any time — even after closing this tab.');}catch(_e){toast('This browser blocked saving the pin. Export the report instead.');}renderPinStrip();}
function clearPin(){try{localStorage.removeItem(PIN_KEY);}catch(_e){}toast('Pinned run removed.');renderPinStrip();}
function barDeltaCell(pinValue,curValue,unit='bars'){if(!Number.isFinite(pinValue)||!Number.isFinite(curValue))return element('span','—','muted');const diff=curValue-pinValue;if(!diff)return element('span','same count','muted');return element('span',`${diff>0?'+':''}${number(diff,0)} ${unit}`,diff>0?'positive':'');}
function ppDeltaCell(pinFrac,curFrac,lowerIsBetter){if(![pinFrac,curFrac].every(Number.isFinite))return element('span','—','muted');const diffPp=(curFrac-pinFrac)*100;if(Math.abs(diffPp)<1e-9)return element('span','same','muted');const better=lowerIsBetter?diffPp<0:diffPp>0;return element('span',`${diffPp>0?'+':''}${number(diffPp)}pp · ${better?'better':'worse'}`,better?'positive':'negative');}
function renderPinStrip(){
  const strip=$('#pinned-strip');const pinBtn=$('#pin-report');
  const pinData=readPin();
  if(pinBtn)pinBtn.disabled=!report;
  if(!strip)return;
  if(!pinData){strip.hidden=true;strip.replaceChildren();return;}
  strip.hidden=false;
  const parts=[];
  if(pinData)parts.push(element('p',`${pinData.symbol} · fingerprint ${pinData.fingerprint.slice(0,10)}… · pinned ${new Date(pinData.pinned_at).toLocaleString()}`,'caption pin-summary'));
  if(pinData){
    const row=element('div',null,'button-row pin-actions');
    const cmp=element('button','Compare pinned ↔ current','button primary small');cmp.type='button';
    if(!report||pinData.fingerprint===report.data_fingerprint){cmp.disabled=true;if(report)cmp.title='The open run is the same fingerprint — nothing to compare.';}
    cmp.addEventListener('click',()=>renderPinStrip());
    row.append(cmp);
    const unp=element('button','Unpin','button secondary small');unp.type='button';unp.addEventListener('click',clearPin);row.append(unp);
    parts.push(row);
    if(report&&pinData.fingerprint===report.data_fingerprint)parts.push(element('p','This run is the same fingerprint as the pinned run — same dataset, same settings: nothing honest to compare.','caption'));
    if(report&&pinData.fingerprint!==report.data_fingerprint){parts.push(buildPinCompare(pinData,report));}
    else if(!report)parts.push(element('p','The pinned run is stored. Open or reload the live report to compare against it.','caption'));
  }
  strip.replaceChildren(...parts);
}
function buildPinCompare(pin,cur){
  const wrap=element('div',null,'pin-compare');
  wrap.append(element('h3','Pinned run ↔ current run'));
  const same=pin.fingerprint===cur.data_fingerprint;
  wrap.append(table(['Metric','Pinned run','Current run','Change'],[
    ['Dataset',pin.symbol||'—',currentSymbol||'—',same?'same fingerprint':'different dataset / settings'],
    ['Test window',`${pin.report.test_start?.slice(0,10)??'—'} → ${pin.report.test_end?.slice(0,10)??'—'}`,`${cur.test_start?.slice(0,10)??'—'} → ${cur.test_end?.slice(0,10)??'—'}`,'dates, not compared'],
    ['Supplied bars',number(pin.report.bars,0),number(cur.bars,0),barDeltaCell(pin.report.bars,cur.bars)],
    ['Net return after costs',pct(pin.report.summary.total_return),pct(cur.summary.total_return),ppDeltaCell(pin.report.summary.total_return,cur.summary.total_return,false)],
    ['Closed-trade win rate',pct(pin.report.summary.win_rate),pct(cur.summary.win_rate),ppDeltaCell(pin.report.summary.win_rate,cur.summary.win_rate,false)],
    ['Maximum drawdown',pct(pin.report.summary.max_drawdown),pct(cur.summary.max_drawdown),ppDeltaCell(pin.report.summary.max_drawdown,cur.summary.max_drawdown,true)],
    ['Closed trades',number(pin.report.summary.total_trades,0),number(cur.summary.total_trades,0),barDeltaCell(pin.report.summary.total_trades,cur.summary.total_trades,'trades')],
    ['Verdict',pin.report.status==='paper_candidate'?'Paper candidate':'More evidence needed',cur.status==='paper_candidate'?'Paper candidate':'More evidence needed',same?'same fingerprint':'per-run verdict']
  ]));
  wrap.append(element('p','Comparing two stored evidence snapshots. The change column describes these two runs only — it reads past results, it does not forecast anything. Each run keeps its own regime table and cost grid above.','caption pin-note'));
  return wrap;
}
$('#pin-report').addEventListener('click',writePin);
renderPinStrip();

// PLAIN-ENGLISH RUN SUMMARY — the note #6 upgrade. Written from the report's
// own numbers so the user can paste an honest evidence card anywhere.
let runShareText='';
function renderRunSummary(){
  const host=$('#run-summary'),copy=$('#copy-run-summary');
  if(!host)return;
  if(!report){host.hidden=true;host.replaceChildren();runShareText='';if(copy)copy.disabled=true;return;}
  const s=report.summary||{},config=report.config||{};
  const ci=Array.isArray(s.win_rate_ci95)&&s.win_rate_ci95.length===2?s.win_rate_ci95:null;
  const folds=Number(report.trial_count)||0;
  const verdict=report.status==='paper_candidate'?'Cleared as a paper candidate.':'Not yet a paper candidate — more evidence needed.';
  const core=[verdict,
    `On unseen test windows ${String(report.test_start).slice(0,10)} → ${String(report.test_end).slice(0,10)} (${report.bars} supplied bars of ${currentSymbol||'the dataset'}), the parameters returned ${pct(s.total_return)} after ${number(config.fee_bps,0)} bps fees and ${number(config.slippage_bps,0)} bps slippage per side — ${number(s.total_trades,0)} closed trade${Number(s.total_trades)===1?'':'s'}, win rate ${pct(s.win_rate)}${ci?` (95% range ${pct(ci[0])}–${pct(ci[1])})`:''}, maximum drawdown ${pct(Math.abs(Number(s.max_drawdown)||0))}, across ${folds?`${folds} walk-forward fold${folds===1?'':'s'}`:'the walk-forward folds'}.`,
    'One dataset, one parameter family: this is evidence to collect more of, not a forecast of what happens next; the regime and cost tables slice the same past, nothing more.'].join(' ');
  runShareText=`${core} Verified by Loki walk-forward research · fingerprint ${String(report.data_fingerprint||'').slice(0,10)}…`;
  host.textContent=core;
  host.hidden=false;
  if(copy)copy.disabled=false;
  const pinData=readPin();
  if(pinData&&pinData.fingerprint!==report.data_fingerprint){
    const jump=element('button','Compare with the pinned run ↓','text-link jump-pin');jump.type='button';
    jump.addEventListener('click',()=>{const strip=$('#pinned-strip');if(strip){strip.scrollIntoView({block:'center',behavior:'smooth'});strip.classList.add('pin-flash');setTimeout(()=>strip.classList.remove('pin-flash'),1700);}});
    host.append(document.createElement('br'),jump);
  }
}
$('#copy-run-summary').addEventListener('click',async()=>{
  if(!report||!runShareText)return;
  let copied=false;
  try{await navigator.clipboard.writeText(runShareText);copied=true;}
  catch(_e){try{const box=document.createElement('textarea');box.value=runShareText;box.style.position='fixed';box.style.opacity='0';document.body.append(box);box.select();copied=document.execCommand('copy');box.remove();}catch(_e2){copied=false;}}
  toast(copied?'Run summary copied — paste it anywhere as an honest evidence card.':'This browser blocked the clipboard. Export the report instead.');
});

// CHOSEN-FILE LABEL — the upload zone tells you what is loaded before you run.
const dataFileInput=$('#data-file'),fileLabel=$('#file-label');
if(dataFileInput&&fileLabel)dataFileInput.addEventListener('change',()=>{
  const file=dataFileInput.files&&dataFileInput.files[0];
  // A file picked by hand re-arms real-data mode; a generated practice file keeps its seed.
  if(file&&file.name.startsWith('synthetic-practice'))practiceDataset=true;
  else{practiceDataset=false;practiceSeed=null;}
  if(file)fileLabel.textContent=`✓ Selected: ${file.name} · ${(file.size/1024).toFixed(0)} KB`;
  else fileLabel.textContent='Choose historical OHLCV data';
});
$('#generate-practice').addEventListener('click',generatePracticeDataset);
