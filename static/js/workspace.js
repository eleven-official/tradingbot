'use strict';
const $ = (selector) => document.querySelector(selector);
let report = null;
let reportTime = null;
let sizing = null;
let riskRevision = 0;
let previousIntent = 'help';
const pct = (value) => value == null ? '—' : `${(value * 100).toFixed(2)}%`;
const number = (value, digits=2) => value == null ? '—' : Number(value).toLocaleString(undefined, {maximumFractionDigits:digits});
const numericForm = (form) => Object.fromEntries([...new FormData(form)].map(([key, value]) => [key, Number(value)]));
async function post(url, payload) {
  const response = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : (data.detail || []).map(item => `${item.loc?.join('.')}: ${item.msg}`).join('\n') || 'Request failed.');
  return data;
}
function csvRows(text) {
  const rows = []; let row = [], value = '', quoted = false;
  for (let i=0; i<text.length; i++) {
    const char = text[i];
    if (char === '"') { if (quoted && text[i+1] === '"') {value+='"'; i++;} else quoted=!quoted; }
    else if (char === ',' && !quoted) {row.push(value.trim()); value='';}
    else if ((char === '\n' || char === '\r') && !quoted) {if (char === '\r' && text[i+1] === '\n') i++; row.push(value.trim()); if(row.some(Boolean)) rows.push(row); row=[]; value='';}
    else value += char;
  }
  if (quoted) throw new Error('CSV has an unclosed quoted field.');
  row.push(value.trim()); if(row.some(Boolean)) rows.push(row);
  return rows;
}
function parseBars(text) {
  const rows = csvRows(text.replace(/^\uFEFF/,''));
  const headers = (rows.shift() || []).map(value=>value.toLowerCase());
  const required=['timestamp','open','high','low','close','volume'];
  if (required.some(key => !headers.includes(key)) || new Set(headers).size !== headers.length) throw new Error('Use unique CSV columns: timestamp, open, high, low, close, volume.');
  if (rows.length < 161 || rows.length > 5000) throw new Error('Upload between 161 and 5,000 bars from one asset.');
  return rows.map((row,index) => {
    if(row.length !== headers.length) throw new Error(`CSV row ${index+2} has the wrong number of columns.`);
    const bar = {};
    for (const key of required) {
      const raw=row[headers.indexOf(key)];
      if(!raw) throw new Error(`CSV row ${index+2}: ${key} is empty.`);
      if(key==='timestamp') bar[key]=raw;
      else {const value=Number(raw); if(!Number.isFinite(value)) throw new Error(`CSV row ${index+2}: ${key} must be a number.`); bar[key]=value;}
    }
    return bar;
  });
}
function cell(row, text) {const td=document.createElement('td'); td.textContent=text; row.append(td);}
function renderReport() {
  const metrics=report.summary;
  $('#return-metric').textContent=pct(metrics.total_return);
  $('#return-metric').className=metrics.total_return>=0?'positive':'negative';
  $('#drawdown-metric').textContent=pct(metrics.max_drawdown);
  $('#winrate-metric').textContent=pct(metrics.win_rate);
  $('#trades-metric').textContent=`${metrics.total_trades} closed trades · 95% interval ${metrics.win_rate_ci95 ? metrics.win_rate_ci95.map(pct).join('–') : 'unavailable'}`;
  $('#verdict-metric').textContent=report.status==='paper_candidate'?'Paper candidate':'More evidence needed';
  $('#research-details').hidden=false;
  const evidence=$('#evidence-list'); evidence.replaceChildren();
  for (const reason of [...report.rejection_reasons, ...report.assumptions]) {const li=document.createElement('li');li.textContent=reason;evidence.append(li);}
  const table=document.createElement('table');
  const head=document.createElement('tr'); for(const title of ['Cost multiplier','Net return','Drawdown']) {const th=document.createElement('th');th.textContent=title;head.append(th);} table.append(head);
  for (const scenario of report.cost_stress) {const row=document.createElement('tr');cell(row,`${scenario.multiplier}×`);cell(row,pct(scenario.total_return));cell(row,pct(scenario.max_drawdown));table.append(row);} $('#stress-table').replaceChildren(table);
  const folds=$('#fold-table');folds.replaceChildren();
  for (const fold of report.folds) {const row=document.createElement('tr');cell(row,fold.test_start.slice(0,10));cell(row,fold.test_end.slice(0,10));cell(row,JSON.stringify(fold.parameters));cell(row,pct(fold.metrics.total_return));folds.append(row);}
  $('#report-statistics').textContent=`Expectancy: ${number(metrics.expectancy)} / trade · Profit factor: ${metrics.profit_factor==null?'not estimable':number(metrics.profit_factor)} · Estimated fees: ${number(metrics.total_fees)} · Slippage: ${number(metrics.total_slippage)} · ${report.trial_count} training trials`;
  $('#chart-empty').hidden=true; $('#equity-chart').hidden=false;
  $('#chart-caption').textContent=`Historical forward tests: ${report.test_start.slice(0,10)} → ${report.test_end.slice(0,10)} · ${report.bars} supplied bars · Data fingerprint ${report.data_fingerprint.slice(0,16)}… · Values in input quote currency`;
  drawChart();
}
function drawChart() {
  if(!report) return;
  const canvas=$('#equity-chart'), width=canvas.clientWidth, height=280, scale=window.devicePixelRatio||1;
  canvas.width=width*scale;canvas.height=height*scale;const ctx=canvas.getContext('2d');ctx.scale(scale,scale);
  const initial={timestamp:report.test_start,equity:report.config.initial_capital,benchmark_equity:report.config.initial_capital};
  const points=[initial,...report.equity_curve];
  const values=points.flatMap(point=>[point.equity,point.benchmark_equity]);
  const min=Math.min(...values), max=Math.max(...values), padding=Math.max((max-min)*.12,max*.005,1), low=min-padding, high=max+padding;
  const left=60,right=12,top=14,bottom=30;
  const x=(i)=>left+i/(points.length-1)*(width-left-right), y=(v)=>top+(high-v)/(high-low)*(height-top-bottom);
  ctx.font='10px Segoe UI';ctx.lineWidth=1;
  for(let i=0;i<5;i++){const val=low+(high-low)*i/4;ctx.strokeStyle='#24303b';ctx.beginPath();ctx.moveTo(left,y(val));ctx.lineTo(width-right,y(val));ctx.stroke();ctx.fillStyle='#8b9fad';ctx.fillText(number(val,0),0,y(val)+3);}
  for(const [key,color] of [['benchmark_equity','#708393'],['equity','#a4e6bc']]){ctx.beginPath();ctx.strokeStyle=color;ctx.lineWidth=key==='equity'?2:1.5;ctx.setLineDash(key==='equity'?[]:[5,4]);points.forEach((point,i)=>i?ctx.lineTo(x(i),y(point[key])):ctx.moveTo(x(i),y(point[key])));ctx.stroke();}
  ctx.setLineDash([]);ctx.fillStyle='#8b9fad';ctx.fillText(points[0].timestamp.slice(0,10),left,height-7);ctx.textAlign='right';ctx.fillText(points.at(-1).timestamp.slice(0,10),width-right,height-7);
}
$('#data-file').addEventListener('change',event=>{$('#file-label').textContent=event.target.files[0]?.name||'Choose historical OHLCV data';});
$('#research-form').addEventListener('submit',async event=>{
  event.preventDefault(); const file=$('#data-file').files[0];if(!file)return;
  const message=$('#research-message'),button=$('#run-research');button.disabled=true;message.className='form-message';message.textContent='Validating history and evaluating unseen windows…';
  try{if(file.size>3_000_000)throw new Error('Choose a CSV smaller than 3 MB.');const bars=parseBars(await file.text());const config=numericForm(event.target);config.periods_per_year=Number(config.periods_per_year);report=await post('/api/research/evaluate',{bars,config});reportTime=new Date().toISOString();renderReport();message.textContent='Research complete. Review the costs, test windows, and limitations below.';}
  catch(error){message.className='form-message error';message.textContent=`${error.message}${report?' Previous successful report remains displayed.':''}`;}finally{button.disabled=false;}
});
$('#download-report').addEventListener('click',()=>{if(!report)return;const blob=new Blob([JSON.stringify(report,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`loki-research-${report.data_fingerprint.slice(0,12)}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
$('#risk-form').addEventListener('input',()=>{riskRevision++;sizing=null;$('#risk-result').textContent='Inputs changed. Calculate again to refresh the preview.';});
$('#risk-form').addEventListener('submit',async event=>{
  event.preventDefault();sizing=null;const revision=riskRevision,button=event.target.querySelector('button');button.disabled=true;
  try{
    const result=await post('/api/risk/preview',numericForm(event.target));
    if(revision!==riskRevision)return;
    sizing=result;
    $('#risk-result').textContent=`Quantity: ${number(sizing.quantity,8)} units\nCash required: ${number(sizing.cash_required)}\nPlanned loss at stop: ${number(sizing.planned_loss_at_stop)} / ${number(sizing.risk_budget)} budget\nBinding limit: ${sizing.binding_limit}. Preview only; no order submitted.`;
  }catch(error){if(revision===riskRevision)$('#risk-result').textContent=error.message;}
  finally{button.disabled=false;}
});
function addChat(text,role) {const div=document.createElement('div');div.className=`chat-message ${role}`;const label=document.createElement('span');label.textContent=role==='user'?'YOU':'LOKI';const body=document.createElement('p');body.textContent=text;div.append(label,body);const log=$('#chat-messages');log.append(div);while(log.children.length>40)log.firstElementChild.remove();log.scrollTop=log.scrollHeight;}
async function sendChat(message) {
  const button=$('#chat-form button'),input=$('#chat-input');if(button.disabled)return;button.disabled=true;input.disabled=true;addChat(message,'user');input.value='';
  try{const context={data_mode:report?'uploaded historical CSV (unverified)':'no dataset supplied',trading_mode:'research only',as_of:reportTime||'no research run yet',previous_intent:previousIntent};if(report){context.latest_backtest=report;context.strategy=report.strategy;}if(sizing)context.position_preview=sizing;
    const reply=await post('/api/copilot',{message,context});previousIntent=reply.intent;addChat(reply.text,'assistant');const prompts=$('#chat-prompts');prompts.replaceChildren();for(const suggestion of reply.suggestions.slice(0,3)){const b=document.createElement('button');b.type='button';b.textContent=suggestion;b.dataset.prompt=suggestion;prompts.append(b);}}
  catch(error){addChat(`I couldn't complete that request. ${error.message}`,'assistant');}finally{button.disabled=false;input.disabled=false;input.focus();}
}
$('#chat-form').addEventListener('submit',event=>{event.preventDefault();const message=$('#chat-input').value.trim();if(message)sendChat(message);});
$('#chat-prompts').addEventListener('click',event=>{const button=event.target.closest('[data-prompt]');if(button)sendChat(button.dataset.prompt);});
for(const link of document.querySelectorAll('.sidebar nav a'))link.addEventListener('click',()=>{document.querySelector('.sidebar nav .active')?.classList.remove('active');link.classList.add('active');});
new ResizeObserver(drawChart).observe($('#equity-chart'));
