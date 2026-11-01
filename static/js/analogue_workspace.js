'use strict';
(() => {
  const host=document.getElementById('simulated-market');
  if(!host||document.getElementById('analogue-research'))return;
  const panel=element('section','','panel');
  panel.id='analogue-research';
  panel.innerHTML=`<p class="eyebrow">NEW MODEL / HISTORICAL ANALOGUES / RESEARCH ONLY</p>
    <h2>What followed similar market conditions?</h2>
    <p class="muted">A separate model compares earlier patterns within similar trend/volatility regimes, calibrates confidence on a dedicated earlier period and reports the distribution of what followed. It does not submit orders or replace your existing runner.</p>
    <form id="analogue-form"><fieldset><div class="form-grid two-col">
      <label>Instrument<select name="symbol"><option>SPY</option><option>QQQ</option><option>ES</option><option>NQ</option><option>MES</option><option>MNQ</option><option>AAPL</option><option>MSFT</option><option>NVDA</option><option>TSLA</option></select></label>
      <label>Bar interval<select name="timeframe"><option value="1d">Daily · not day-trading evidence</option><option value="5m">5 minutes</option><option value="15m">15 minutes</option><option value="30m">30 minutes</option><option value="1h">1 hour</option></select></label>
      <label>Actual historical window<select name="years"><option>20</option><option>15</option><option>10</option></select></label>
      <label>Forecast horizon · bars<input name="horizon" type="number" min="1" max="12" value="3" required></label>
      <label>Commission · USD per side/share or contract<input name="commission" type="number" min="0.001" max="100" step="0.001" value="0.01" required></label>
      <label>Slippage · ticks per side<input name="slippage_ticks" type="number" min="1" max="20" step="0.25" value="1" required></label>
      <label>Data source / provenance<input name="source" maxlength="200" value="Operator CSV · verify vendor rights and adjustments" required></label>
      <label>Historical CSV · up to 500,000 bars<input name="history" type="file" accept=".csv,text/csv"></label>
    </div><div class="button-row"><button class="button secondary" type="submit">Train and evaluate new analogue model</button><button class="button secondary" type="button" id="analogue-use-snapshot">Use selected saved daily snapshot</button></div></fieldset></form>
    <p class="caption">Intraday CSV needs timestamp, open, high, low, close, volume, session. Use completed timezone-aware bar-close timestamps and exchange trading-session dates. Futures also require the actual contract (for example ESZ2020). Roll/session/gap crossings are excluded, not reconstructed. Licensed intraday data must be supplied; daily downloads are not intraday history.</p>
    <p id="analogue-message" class="form-message" role="status"></p><div id="analogue-result"></div>
    <details open><summary>Saved models / estimate next horizon</summary><label>Saved research<select id="analogue-saved-models"><option value="">Load saved model catalog</option></select></label><label>Saved model ID<input id="analogue-model-id" maxlength="64" pattern="[a-f0-9]{64}"></label><div class="button-row"><button class="button secondary" id="analogue-refresh" type="button">Refresh saved models</button><button class="button secondary" id="analogue-load" type="button">Load saved research</button><button class="button secondary" id="analogue-latest" type="button" disabled>Latest completed daily estimate</button></div><label>Or upload latest 20–10,000 completed bars · same CSV columns<input id="analogue-new-bars" type="file" accept=".csv,text/csv"></label><button class="button secondary" id="analogue-forecast" type="button">Estimate from uploaded bars</button><div id="analogue-forecast-result"></div></details>`;
  host.prepend(panel);
  const form=panel.querySelector('form'), messageNode=panel.querySelector('#analogue-message');
  let busy=false,selectedReport=null,activeVersion=null;
  const picker=panel.querySelector('#analogue-saved-models');
  function controls(){
    panel.querySelector('#analogue-latest').disabled=busy||!selectedReport||selectedReport.version!==activeVersion||selectedReport.timeframe!=='1d'||!selectedReport.source.startsWith('Yahoo Finance via yfinance');
  }
  async function perform(task){
    if(busy)return;
    busy=true;panel.querySelectorAll('button').forEach(b=>b.disabled=true);
    try{
      if(!capabilities)await loadCapabilities();
      if(!capabilities?.local_actions_enabled)throw Error('Analogue research needs the local Loki launcher and its private session token.');
      await task();
    }catch(error){messageNode.textContent=error.message;}
    finally{busy=false;panel.querySelectorAll('button').forEach(b=>b.disabled=false);controls();}
  }
  function csv(text,min,max){
    const rows=csvRows(text.replace(/^\uFEFF/,'')), headers=(rows.shift()||[]).map(x=>x.toLowerCase());
    const required=['timestamp','open','high','low','close','volume'];
    if(new Set(headers).size!==headers.length||required.some(k=>!headers.includes(k)))throw Error('CSV needs unique timestamp, open, high, low, close, volume columns.');
    if(rows.length<min||rows.length>max)throw Error(`Supply ${min}–${max} bars.`);
    return rows.map((row,index)=>{
      if(row.length!==headers.length)throw Error(`CSV row ${index+2} has the wrong number of columns.`);
      const bar={};
      for(const key of [...required,...['session','contract'].filter(k=>headers.includes(k))]){
        const raw=row[headers.indexOf(key)];
        if(!raw)throw Error(`CSV row ${index+2}: missing ${key}`);
        bar[key]=['timestamp','session','contract'].includes(key)?raw:Number(raw);
        if(typeof bar[key]==='number'&&!Number.isFinite(bar[key]))throw Error(`CSV row ${index+2}: invalid ${key}`);
      }
      return bar;
    });
  }
  async function read(file,min,max){
    if(!file)throw Error('Choose a CSV file first.');
    if(file.size>80000000)throw Error('CSV must be at most 80 MB.');
    return csv(await file.text(),min,max);
  }
  function settings(){
    const data=new FormData(form), values={};
    for(const k of ['symbol','timeframe','source'])values[k]=String(data.get(k));
    for(const k of ['years','horizon','commission','slippage_ticks'])values[k]=Number(data.get(k));
    return values;
  }
  form.elements.symbol.addEventListener('change',()=>{
    form.elements.commission.value=['ES','NQ','MES','MNQ'].includes(form.elements.symbol.value)?'2.5':'0.01';
  });
  function forecastView(value,target){
    target.replaceChildren();
    if(!value){target.append(element('p','The last window crosses a gap/session/roll; no latest forecast is available.','muted'));return;}
    target.append(inlineMetrics([['Research view',value.decision],['Calibrated up estimate',pct(value.estimated_up_probability??value.up_frequency_smoothed)],['Median next-horizon return',pct(value.return_quantiles.p50)],['Historical 10–90% range',`${pct(value.return_quantiles.p10)} to ${pct(value.return_quantiles.p90)}`]]));
    target.append(element('p',`${value.as_of} · raw similar-case frequency ${pct(value.up_frequency_smoothed)} · ${value.reference_regime||'legacy pool'}. Calibration is estimated from earlier dates, not a guarantee of future accuracy or ranges. No order is sent.`,'caption'));
    if(value.abstention_reasons?.length)target.append(bulletList(value.abstention_reasons));
    target.append(table(['Historical signal','Outcome date','Gross move','Distance'],value.analogues.map(a=>[a.signal_at,a.outcome_at,pct(a.gross_return),number(a.distance,3)])));
  }
  function render(report){
    selectedReport=report;
    panel.querySelector('#analogue-model-id').value=report.id;
    if(Array.from(picker.options).some(option=>option.value===report.id))picker.value=report.id;
    panel.querySelector('#analogue-forecast-result').replaceChildren();
    const target=panel.querySelector('#analogue-result');
    target.replaceChildren(element('h3',`${report.symbol} · ${human(report.status)}`),
      element('p',`${report.version} · ${report.coverage.bars.toLocaleString()} real bars · ${report.coverage.years.toFixed(2)} years · ${report.timeframe} · ${report.horizon_bars}-bar horizon. ${report.training.references} frozen training references.`,'caption'));
    if(report.calibration)target.append(element('p',`${report.calibration.examples} separate calibration examples · selected analogue weight ${report.calibration.selected_weight}; the remainder shrinks toward the frozen training baseline.`,'caption'));
    if(report.readiness){target.append(element('p',report.readiness.note,'integration-note'));if(report.readiness.reasons.length)target.append(bulletList(report.readiness.reasons));}
    target.append(table(['Chronological period','Calibrated Brier','Raw Brier','Baseline Brier','Signals','Sampled unit P&L','2× cost unit P&L'],['validation','test'].map(key=>{
      const m=report[key];return [key,number(m.brier_score,4),number(m.uncalibrated_brier_score,4),number(m.baseline_brier_score,4),m.signals,number(m.unit_net_pnl),number(m.unit_stress_pnl)];
    })));
    target.append(element('p','P&L is sampled one-share/one-contract opportunity outcomes, not a leveraged account return. The new model is not connected to broker execution.','integration-note'));
    const latest=element('div');forecastView(report.latest,latest);target.append(latest,bulletList(report.limitations));
    const save=element('button','Export research report','button secondary');save.type='button';save.addEventListener('click',()=>exportJSON(report,`loki-analogue-${report.symbol}.json`));target.append(save);
    controls();
  }
  async function refreshCatalog(preferred){
    let catalog;
    try{catalog=await request('/api/fusion/analogue',undefined,true);}catch(error){throw Error(`Saved-model API unavailable. Relaunch the updated local Loki server, then refresh. ${error.message}`);}
    activeVersion=catalog.model_version;
    picker.replaceChildren();
    for(const model of catalog.models)picker.append(new Option(`${model.symbol} · ${model.timeframe} · ${model.coverage.years.toFixed(1)}y · ${model.version} · ${human(model.status)}`,model.id));
    if(!catalog.models.length){picker.append(new Option('No saved analogue models yet',''));messageNode.textContent='No saved model. Train from history or a licensed CSV first.';return;}
    const chosen=catalog.models.find(model=>model.id===preferred)||catalog.models.find(model=>model.version===activeVersion&&model.symbol===form.elements.symbol.value)||catalog.models[0];
    picker.value=chosen.id;panel.querySelector('#analogue-model-id').value=chosen.id;
    render(await request('/api/fusion/analogue/'+chosen.id,undefined,true));
    messageNode.textContent=`Loaded ${chosen.symbol} saved research on ${activeVersion}. ${catalog.unreadable_models?`${catalog.unreadable_models} unreadable bundles were skipped. `:''}${catalog.scan_limit_reached?'Catalog scan is capped; a specific ID can still be loaded.':''}`;
  }
  async function train(bars,config){
    messageNode.textContent='Building earlier-date references, purging horizons and evaluating later dates…';
    const report=await request('/api/fusion/analogue/evaluate',{...config,bars},true);
    await refreshCatalog(report.id);messageNode.textContent='New research bundle saved locally. Earlier models and broker state were not changed.';
  }
  form.addEventListener('submit',event=>{event.preventDefault();perform(async()=>train(await read(form.elements.history.files[0],600,500000),settings()));});
  panel.querySelector('#analogue-use-snapshot').addEventListener('click',()=>perform(async()=>{
    const id=document.getElementById('paper-model-select')?.value;
    if(!id)throw Error('Connect a paper account and select a saved instrument model first.');
    const input=await request('/api/fusion/broker/models/'+id+'/dataset',undefined,true);
    const report=await request('/api/fusion/broker/models/'+id,undefined,true);
    if(report.requested_years<10)throw Error('Choose a 10–20 year saved daily dataset, not a five-year window.');
    form.elements.symbol.value=input.symbol;form.elements.timeframe.value='1d';form.elements.years.value=String(report.requested_years);form.elements.commission.value='0.01';
    const source=input.source.provider||'Saved operator snapshot';form.elements.source.value=source;
    await train(input.bars,{...settings(),symbol:input.symbol,timeframe:'1d',years:report.requested_years,source});
  }));
  panel.querySelector('#analogue-load').addEventListener('click',()=>perform(async()=>{
    const id=panel.querySelector('#analogue-model-id').value.trim();if(!/^[a-f0-9]{64}$/.test(id))throw Error('Enter a saved model ID.');
    render(await request('/api/fusion/analogue/'+id,undefined,true));messageNode.textContent='Loaded frozen local research.';
  }));
  panel.querySelector('#analogue-forecast').addEventListener('click',()=>perform(async()=>{
    const id=panel.querySelector('#analogue-model-id').value.trim();if(!/^[a-f0-9]{64}$/.test(id))throw Error('Enter a saved model ID.');
    const bars=await read(panel.querySelector('#analogue-new-bars').files[0],20,10000);
    const result=await request('/api/fusion/analogue/'+id+'/forecast',{bars},true);
    forecastView(result,panel.querySelector('#analogue-forecast-result'));messageNode.textContent='Research estimate only; broker execution remains disconnected.';
  }));
  panel.querySelector('#analogue-refresh').addEventListener('click',()=>perform(()=>refreshCatalog(panel.querySelector('#analogue-model-id').value.trim())));
  picker.addEventListener('change',()=>{
    panel.querySelector('#analogue-model-id').value=picker.value;selectedReport=null;
    panel.querySelector('#analogue-result').replaceChildren();panel.querySelector('#analogue-forecast-result').replaceChildren();controls();
    messageNode.textContent='Load the selected model to inspect it before requesting an estimate.';
  });
  panel.querySelector('#analogue-model-id').addEventListener('input',()=>{
    if(selectedReport?.id!==panel.querySelector('#analogue-model-id').value.trim()){
      selectedReport=null;panel.querySelector('#analogue-forecast-result').replaceChildren();controls();
    }
  });
  panel.querySelector('#analogue-latest').addEventListener('click',()=>perform(async()=>{
    if(!selectedReport)throw Error('Load a current daily model first.');
    const result=await request('/api/fusion/analogue/'+selectedReport.id+'/forecast-latest',{},true);
    forecastView(result,panel.querySelector('#analogue-forecast-result'));messageNode.textContent=result.data_note;
  }));
  perform(()=>refreshCatalog());
})();
