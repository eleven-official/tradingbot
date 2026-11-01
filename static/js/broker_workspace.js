'use strict';
(()=>{
  let connection=null,model=null,agent=null,busy=false,active=false,timer=null,generation=0,stopping=false;
  const onPaper=()=>location.hash==='#simulated-market'&&!document.hidden;
  const paperConnection=()=>connection?.connected&&connection.provider==='alpaca'&&connection.mode==='paper';
  function controls(){
    $('#broker-disconnect').disabled=busy||!connection?.connected;
    $('#broker-account-refresh').disabled=busy||!connection?.connected;
    $('#instrument-train-fields').disabled=busy||active||!paperConnection();
    $('#paper-model-select').disabled=busy||active||!paperConnection();
    const managing=agent?.model_id===model?.id&&(agent?.pending||agent?.owned_qty>0);
    $('#ai-paper-start').disabled=busy||stopping||active||!onPaper()||!paperConnection()||!model||connection.account.trading_blocked||(!managing&&model?.execution_readiness?.can_start!==true);
    $('#ai-paper-stop').disabled=stopping||(!active&&!agent?.running);$('#ai-paper-reconcile').disabled=busy||stopping||!paperConnection()||!agent?.model_id;$('#ai-paper-cancel').disabled=busy||stopping||!paperConnection()||!agent?.pending;
    $('#broker-connect-form button[type=submit]').disabled=busy;
    $('#ai-max-notional').disabled=busy||active;
    const compare=$('#compare-paper-strategies');
    if(compare)compare.disabled=busy||active||!paperConnection()||model?.artifact?.version!=='loki_instrument_daily_logistic_v1';
  }
  async function ready(){if(!capabilities)await loadCapabilities();if(!capabilities?.local_actions_enabled)throw new Error('Broker key entry and AI paper trading need the local Loki launcher.');}
  async function perform(task,target){if(busy)return;busy=true;controls();try{await ready();await task();}catch(error){message(target,error.message,true);}finally{busy=false;controls();}}
  function accountCard(){
    for(const target of ['#broker-paper-account','#broker-live-account']){
      const node=$(target);node.replaceChildren();
      if(!connection?.connected){node.append(element('p','No broker account is linked in this browser.','muted'));continue;}
      const account=connection.account;
      node.append(element('p',`${connection.provider.toUpperCase()} · ${connection.mode.toUpperCase()} · ${account.status||'verified'}`,'integration-note'));
      if(connection.provider==='alpaca'){
        node.append(inlineMetrics([['Broker cash',number(account.cash)+' USD'],['Broker equity',number(account.equity)+' USD'],['Account ending',account.id_hint]]));
        const holdings=Array.isArray(connection.positions)?connection.positions:null;
        if(!holdings)node.append(element('p','Holdings could not be read from the venue right now — nothing was invented to fill the gap.','caption'));
        else{
          node.append(element('p',"WHAT THE ACCOUNT HOLDS",'eyebrow'));
          if(!holdings.length)node.append(element('p',"No open positions right now — Loki sees a cash-only paper account.",'muted'));
          else node.append(table(['Symbol','Units','Entry','Mark','Value','Open P&L'],holdings.map(item=>[item.symbol,item.qty,number(item.avg_entry_price),number(item.current_price),number(item.market_value),number(item.unrealized_pl)])));
        }
      }
      else node.append(table(['Asset','Total units','Available units'],(account.assets||[]).map(a=>[a.currency,number(a.total,8),number(a.free,8)])));
      node.append(element('p',connection.credential_storage,'caption'));
    }
    $('#broker-paper-status').textContent=paperConnection()?'Alpaca paper connected':connection?.connected?'Paper account required':'Not connected';
    $('#broker-live-status').textContent=connection?.connected?`${connection.provider} / ${connection.mode}`:'No browser account linked';window.dispatchEvent(new CustomEvent('loki-broker-connection',{detail:connection}));
    controls();
  }
  function showModel(report){
    model=report;const target=$('#instrument-model-results');target.hidden=false;
    target.replaceChildren(element('h3',`${report.symbol} · ${report.coverage.years.toFixed(2)} years received`),inlineMetrics([['Daily observations',number(report.coverage.bars,0)],['Later-test net return',pct(report.test.net_return)],['Completed test trades',number(report.test.closed_trades,0)],['Observed test win rate',pct(report.test.win_rate)]]));
    target.append(element('p',`Research source: ${report.source.provider||report.source.name||'Operator upload'} · actual dates ${report.coverage.start}–${report.coverage.end}. Alpaca remains a separate paper-execution venue.`,'caption'));
    const tested=Number.isFinite(report.test.net_return)&&report.test.closed_trades>0;
    const positive=tested&&report.test.net_return>0&&report.test.expectancy_usd>0;
    const assessment=element('div','','model-evidence');
    assessment.dataset.result=tested?(positive?'positive':'negative'):'unmeasured';
    assessment.append(element('strong',!tested?'Profitability not demonstrated — no completed test trades':positive?'Positive historical result — future profitability unproven':'Unprofitable on unseen history after costs'));
    assessment.append(element('p',tested?`${report.test.closed_trades} closed trades · ${pct(report.test.net_return)} net return · ${number(report.test.expectancy_usd)} USD average per trade. Validation selects the settings; this later test measures whether they held up.`:'The selected policy stayed in cash. A zero return with no trades is not evidence of a profitable strategy.'));
    if(report.artifact.policy)assessment.append(element('p',`Replay costs per side: ${number(report.artifact.policy.fee_bps)} bps fee + ${number(report.artifact.policy.slippage_bps)} bps slippage. Broker execution checks are separate from strategy performance.`, 'caption'));
    target.append(assessment);
    if(report.execution_readiness){
      target.append(element('h3',`Paper entry checks: ${human(report.execution_readiness.status)}`));
      target.append(bulletList(report.execution_readiness.reasons));
      target.append(element('p',report.execution_readiness.note,'caption'));
    }
    if(report.comparison){
      target.append(element('h3',`Frozen validation choice: ${human(report.comparison.selection)}`));
      target.append(element('p','Previously inspected history · development comparison. New forward-paper results have not yet been observed.','integration-note'));
      target.append(table(['Candidate','Validation net','2× cost validation','Positive blocks','Later diagnostic net','Later trades'],report.validation.trials.map(trial=>{
        const later=report.comparison.candidates.find(item=>item.rule===trial.rule);
        return [human(trial.rule)+(trial.rule===report.comparison.selection?' · selected':''),pct(trial.net_return),pct(trial.stress.net_return),`${trial.positive_folds} / 3`,pct(later?.net_return),number(later?.closed_trades,0)];
      })));
      target.append(inlineMetrics([['Selected policy · 2× costs',pct(report.cost_stress.net_return)],['Prior model · later net',pct(report.comparison.baseline_test.net_return)],['Passive 10% allocation',pct(report.test.buy_and_hold_10pct_net_return)],['Selected policy · estimated costs',number(report.test.estimated_costs_usd)+' USD']]));
      target.append(element('p',`Frozen after history ending ${report.forward_evidence.historical_end}. Positive retrospective P&L is not confirmed future edge; cost sensitivity and underperformance versus passive exposure remain visible.`,'caption'));
    }
    target.append(element('p',`${human(report.status)}. Training ${report.training.start}–${report.training.end}; validation ${report.validation.start}–${report.validation.end}; test ${report.test.start}–${report.test.end}.`,'caption'));
    const interval=report.test.win_rate_95pct_interval;target.append(element('p',`Test expectancy ${number(report.test.expectancy_usd)} USD; maximum drawdown ${pct(report.test.max_drawdown)}. Win-rate interval ${interval?interval.map(pct).join('–'):'unavailable'}. Entry threshold ${report.artifact.threshold??'none: wait in cash'}. These results do not prove 70% future wins.`,'integration-note'));
    target.append(element('p',`Matched passive 10% allocation: ${pct(report.test.buy_and_hold_10pct_net_return)}; cash baseline: 0%.`,'caption'));target.append(bulletList(report.limitations),detailsJSON(report,'Inspect frozen model, source and evaluation'));
    const save=element('button','Export model report ↓','button secondary');save.type='button';save.addEventListener('click',()=>exportJSON(report,`loki-${report.symbol.replaceAll('/','-')}-paper-model.json`));const data=element('button','Export exact training input ↓','button secondary');data.type='button';data.addEventListener('click',()=>perform(async()=>{exportJSON(await request('/api/fusion/broker/models/'+report.id+'/dataset',undefined,true),`loki-${report.symbol.replaceAll('/','-')}-PRIVATE-training-input.json`);},'#instrument-train-message'));target.append(save,data);controls();
  }
  async function loadModels(selected){
    if(!paperConnection())return;
    const data=await request('/api/fusion/broker/models',undefined,true),select=$('#paper-model-select');select.replaceChildren();
    if(!data.models.length){select.append(new Option('Train an instrument model first',''));model=null;$('#instrument-model-results').hidden=true;return;}
    for(const item of data.models)select.append(new Option(`${item.symbol} · ${item.coverage.years.toFixed(1)} years · ${human(item.status)}`,item.id));
    if(selected)select.value=selected;
    if(select.value)showModel(await request('/api/fusion/broker/models/'+select.value,undefined,true));
  }
  function renderAgent(){
    if(!agent){$('#ai-paper-metrics').replaceChildren();$('#ai-paper-journal').replaceChildren();controls();return;}
    message('#ai-paper-message',agent.message||'Paper runner ready.');
    const rule=agent.signal_kind==='rule';
    $('#ai-paper-metrics').replaceChildren(inlineMetrics([['Runner',active?'Running on this page':'Paused on this page'],['Owned units',number(agent.owned_qty,6)],[rule?'Entry condition':'Direction score',rule?(agent.probability==null?'Not evaluated':agent.probability===1?'Met':'Not met'):pct(agent.probability)],['Entry threshold',agent.threshold==null?'Wait in cash':rule?'Fixed rule':pct(agent.threshold)]]));
    $('#ai-paper-journal').replaceChildren(agent.journal?.length?table(['Time / UTC','Paper order','State','Actual filled units'],agent.journal.map(row=>[new Date(row.created_at*1000).toISOString().replace('T',' ').slice(0,19),`${row.request.side} ${row.request.qty} ${row.request.symbol} @ ${row.request.limit_price}`,human(row.state),number(row.order?.filled_qty,6)])):element('p','No AI paper order claims yet.','muted'));controls();
  }
  async function refresh(){
    connection=await request('/api/fusion/broker/connection',undefined,true);
    if(connection.connected)try{connection=await request('/api/fusion/broker/account',{},true);}catch(error){/* keep the connection facts; holdings stay unavailable */}
    accountCard();
    if(paperConnection()){await loadModels();agent=await request('/api/fusion/broker/paper-ai',undefined,true);renderAgent();}
  }
  function openDialog(mode){
    perform(async()=>{$('#broker-connect-dialog').showModal();$('#broker-provider').value='alpaca';$('#broker-connection-mode').value=mode;providerChanged();message('#broker-dialog-message','');},'#broker-message');
  }
  function providerChanged(){const alpaca=$('#broker-provider').value==='alpaca';$('#broker-connection-mode option[value=paper]').disabled=!alpaca;if(!alpaca)$('#broker-connection-mode').value='live';$('#broker-passphrase-label').hidden=$('#broker-provider').value!=='coinbase';}
  $('#broker-provider').addEventListener('change',providerChanged);
  $('#connect-paper-broker').addEventListener('click',()=>openDialog('paper'));$('#connect-live-broker').addEventListener('click',()=>openDialog('live'));
  $('#broker-dialog-close').addEventListener('click',()=>{$('#broker-connect-form').reset();$('#broker-connect-dialog').close();});
  $('#broker-connect-dialog').addEventListener('cancel',()=>$('#broker-connect-form').reset());
  $('#broker-connect-form').addEventListener('submit',event=>{
    event.preventDefault();const data=Object.fromEntries(new FormData(event.target));event.target.querySelectorAll('input[type=password]').forEach(input=>{input.value='';});
    perform(async()=>{await pause();connection=await request('/api/fusion/broker/connect',data,true);try{connection=await request('/api/fusion/broker/account',{},true);}catch(error){/* holdings stay unavailable; nothing invented */}model=null;agent=null;accountCard();await loadModels();if(paperConnection()){try{agent=await request('/api/fusion/broker/paper-ai',undefined,true);}catch(error){agent=null;}}renderAgent();$('#broker-connect-dialog').close();message('#broker-message','Account verified. Keys stay in this server session; no order was sent.');},'#broker-dialog-message');
  });
  $('#broker-account-refresh').addEventListener('click',()=>perform(async()=>{connection=await request('/api/fusion/broker/account',{},true);accountCard();},'#broker-message'));
  $('#broker-disconnect').addEventListener('click',()=>perform(async()=>{await pause();const result=await request('/api/fusion/broker/disconnect',{},true);connection=null;model=null;agent=null;accountCard();renderAgent();$('#instrument-model-results').hidden=true;message('#broker-message',result.message);},'#broker-message'));
  const historyForm=$('#instrument-train-form');
  const yearSelect=historyForm.querySelector('select[name=years]');
  for(const years of [15,20])yearSelect.append(new Option(`${years} years`,String(years)));
  const sourceLabel=element('label','Research history source');
  const sourceSelect=element('select');sourceSelect.name='source';
  sourceSelect.append(new Option('Alpaca IEX · account data entitlement','alpaca'),new Option('Yahoo Finance · research only','yahoo'));
  sourceLabel.append(sourceSelect);historyForm.querySelector('.form-grid').append(sourceLabel);
  const historyIntro=historyForm.closest('section').querySelector('p.muted');
  historyIntro.textContent='Research one instrument across 5, 10, 15 or 20 years, then inspect later-period results. Research data and Alpaca paper execution are separate; longer history does not guarantee a forecast or profit.';
  const historyNote=historyForm.nextElementSibling;
  historyNote.textContent='Requested coverage must actually exist: there is no silent provider switch or synthetic padding. Alpaca IEX may not cover long windows; choose Yahoo research history or upload licensed daily CSV data. Dates split chronologically: 60% fit, 20% validation, 20% later evaluation. Select the window before reviewing results.';
  const csvLabel=element('label','Long-history CSV · up to 10,000 daily bars');
  const csvInput=element('input');csvInput.type='file';csvInput.accept='.csv,text/csv';
  csvLabel.append(csvInput);historyForm.querySelector('fieldset').append(csvLabel);
  const csvButton=element('button','Train selected historical CSV','button secondary');csvButton.type='button';
  historyForm.querySelector('fieldset').append(csvButton);
  csvButton.addEventListener('click',()=>perform(async()=>{
    const file=csvInput.files?.[0];if(!file)throw new Error('Choose a daily OHLCV CSV first.');
    if(file.size>4000000)throw new Error('History CSV must be at most 4 MB.');
    const bars=parseBars(await file.text(),10000);
    const data=new FormData(historyForm);
    const result=await request('/api/fusion/broker/train-upload',{symbol:String(data.get('symbol')).toUpperCase(),years:Number(data.get('years')),bars},true);
    await loadModels(result.id);message('#instrument-train-message','Exact CSV snapshot saved. Inspect coverage, source and later-period results before any paper entry.');
  },'#instrument-train-message'));
  $('#instrument-train-form').addEventListener('submit',event=>{
    event.preventDefault();const data=new FormData(event.target),payload={symbol:String(data.get('symbol')).toUpperCase(),years:Number(data.get('years')),source:String(data.get('source'))};
    perform(async()=>{message('#instrument-train-message','Fetching completed daily history and fitting training dates only…');const result=await request('/api/fusion/broker/train-history',payload,true);await loadModels(result.id);message('#instrument-train-message',`Trained on the earlier dates in ${result.coverage.years.toFixed(2)} years of actual history. Later test dates stayed outside model selection.`);},'#instrument-train-message');
  });
  $('#train-imported-instrument').addEventListener('click',()=>perform(async()=>{if(!currentBars)throw new Error('Import daily OHLCV history in Quant lab first.');const years=Number($('#instrument-train-form select[name=years]').value);const result=await request('/api/fusion/broker/train-upload',{symbol:currentSymbol.toUpperCase(),years,bars:currentBars},true);await loadModels(result.id);message('#instrument-train-message','Imported instrument trained. Inspect source assumptions and later-date evaluation.');},'#instrument-train-message'));
  const comparisonButton=element('button','Compare lower-turnover strategies','button secondary');
  comparisonButton.id='compare-paper-strategies';comparisonButton.type='button';
  $('#paper-model-select').closest('label').after(comparisonButton);
  comparisonButton.addEventListener('click',()=>perform(async()=>{
    message('#instrument-train-message','Comparing five development rules against the frozen input, chronological validation and doubled costs…');
    const result=await request('/api/fusion/broker/compare-strategies',{model_id:model.id},true);
    await loadModels(result.id);
    message('#instrument-train-message','Comparison saved. Validation froze the choice; the later results are retrospective diagnostics.');
  },'#instrument-train-message'));
  $('#paper-model-select').addEventListener('change',()=>perform(async()=>{if($('#paper-model-select').value)showModel(await request('/api/fusion/broker/models/'+$('#paper-model-select').value,undefined,true));},'#instrument-train-message'));
  function schedule(){clearTimeout(timer);if(active)timer=setTimeout(cycle,30000);}
  async function cycle(){
    if(!active||!onPaper()){await pause();return;}if(busy){schedule();return;}
    const revision=generation;busy=true;controls();try{const data=await request('/api/fusion/broker/paper-ai/tick',{},true);if(revision===generation){agent=data;active=Boolean(data.running);renderAgent();}}catch(error){active=false;message('#ai-paper-message',error.message,true);}finally{busy=false;controls();schedule();}
  }
  async function pause(){
    const wasRunning=active||agent?.running;active=false;generation++;clearTimeout(timer);
    if(!wasRunning||!paperConnection()){controls();return;}
    stopping=true;controls();try{agent=await request('/api/fusion/broker/paper-ai/stop',{},true);renderAgent();}catch(error){message('#ai-paper-message',`New cycles stopped on this page. ${error.message} Existing venue orders and positions remain.`,true);}finally{stopping=false;controls();}
  }
  $('#ai-paper-start').addEventListener('click',()=>{const max_notional=Number($('#ai-max-notional').value),model_id=model?.id;perform(async()=>{if(!onPaper())throw new Error('Open this Paper screen to start the runner.');agent=await request('/api/fusion/broker/paper-ai/start',{model_id,max_notional},true);active=Boolean(agent.running);generation++;renderAgent();schedule();},'#ai-paper-message').then(()=>{if(active)cycle();});});
  $('#ai-paper-stop').addEventListener('click',pause);
  $('#ai-paper-reconcile').addEventListener('click',()=>perform(async()=>{agent=await request('/api/fusion/broker/paper-ai/reconcile',{},true);renderAgent();},'#ai-paper-message'));
  $('#ai-paper-cancel').addEventListener('click',()=>perform(async()=>{await pause();agent=await request('/api/fusion/broker/paper-ai/cancel-pending',{},true);renderAgent();},'#ai-paper-message'));
  document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();});window.addEventListener('hashchange',()=>{if(!onPaper())pause();controls();});
  window.lokiBrokerWorkspace={isLive:()=>connection?.connected&&connection.mode==='live',summary:()=>connection?.connected?{provider:connection.provider,mode:connection.mode,paper_ai_running:active,model_symbol:model?.symbol}:null};
  controls();perform(refresh,'#broker-message');
})();
