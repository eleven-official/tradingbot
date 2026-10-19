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
    $('#ai-paper-start').disabled=busy||stopping||active||!onPaper()||!paperConnection()||!model||connection.account.trading_blocked;
    $('#ai-paper-stop').disabled=stopping||(!active&&!agent?.running);$('#ai-paper-reconcile').disabled=busy||stopping||!paperConnection()||!agent?.model_id;$('#ai-paper-cancel').disabled=busy||stopping||!paperConnection()||!agent?.pending;
    $('#broker-connect-form button[type=submit]').disabled=busy;
    $('#ai-max-notional').disabled=busy||active;
  }
  async function ready(){if(!capabilities)await loadCapabilities();if(!capabilities?.local_actions_enabled)throw new Error('Broker key entry and AI paper trading need the local Loki launcher.');}
  async function perform(task,target){if(busy)return;busy=true;controls();try{await ready();await task();}catch(error){message(target,error.message,true);}finally{busy=false;controls();}}
  function accountCard(){
    for(const target of ['#broker-paper-account','#broker-live-account']){
      const node=$(target);node.replaceChildren();
      if(!connection?.connected){node.append(element('p','No broker account is linked in this browser.','muted'));continue;}
      const account=connection.account;
      node.append(element('p',`${connection.provider.toUpperCase()} · ${connection.mode.toUpperCase()} · ${account.status||'verified'}`,'integration-note'));
      if(connection.provider==='alpaca')node.append(inlineMetrics([['Broker cash',number(account.cash)+' USD'],['Broker equity',number(account.equity)+' USD'],['Account ending',account.id_hint]]));
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
    $('#ai-paper-metrics').replaceChildren(inlineMetrics([['Runner',active?'Running on this page':'Paused on this page'],['Owned units',number(agent.owned_qty,6)],['Direction score',pct(agent.probability)],['Entry threshold',agent.threshold==null?'Wait in cash':pct(agent.threshold)]]));
    $('#ai-paper-journal').replaceChildren(agent.journal?.length?table(['Time / UTC','Paper order','State','Actual filled units'],agent.journal.map(row=>[new Date(row.created_at*1000).toISOString().replace('T',' ').slice(0,19),`${row.request.side} ${row.request.qty} ${row.request.symbol} @ ${row.request.limit_price}`,human(row.state),number(row.order?.filled_qty,6)])):element('p','No AI paper order claims yet.','muted'));controls();
  }
  async function refresh(){
    connection=await request('/api/fusion/broker/connection',undefined,true);accountCard();
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
    perform(async()=>{await pause();connection=await request('/api/fusion/broker/connect',data,true);model=null;agent=null;accountCard();await loadModels();$('#broker-connect-dialog').close();message('#broker-message','Account verified. Keys stay in this server session; no order was sent.');},'#broker-dialog-message');
  });
  $('#broker-account-refresh').addEventListener('click',()=>perform(async()=>{connection=await request('/api/fusion/broker/account',{},true);accountCard();},'#broker-message'));
  $('#broker-disconnect').addEventListener('click',()=>perform(async()=>{await pause();const result=await request('/api/fusion/broker/disconnect',{},true);connection=null;model=null;agent=null;accountCard();renderAgent();$('#instrument-model-results').hidden=true;message('#broker-message',result.message);},'#broker-message'));
  $('#instrument-train-form').addEventListener('submit',event=>{
    event.preventDefault();const data=new FormData(event.target),payload={symbol:String(data.get('symbol')).toUpperCase(),years:Number(data.get('years'))};
    perform(async()=>{message('#instrument-train-message','Fetching completed daily history and fitting training dates only…');const result=await request('/api/fusion/broker/train-history',payload,true);await loadModels(result.id);message('#instrument-train-message',`Trained on the earlier dates in ${result.coverage.years.toFixed(2)} years of actual history. Later test dates stayed outside model selection.`);},'#instrument-train-message');
  });
  $('#train-imported-instrument').addEventListener('click',()=>perform(async()=>{if(!currentBars)throw new Error('Import daily OHLCV history in Quant lab first.');const years=Number($('#instrument-train-form select[name=years]').value);const result=await request('/api/fusion/broker/train-upload',{symbol:currentSymbol.toUpperCase(),years,bars:currentBars},true);await loadModels(result.id);message('#instrument-train-message','Imported instrument trained. Inspect source assumptions and later-date evaluation.');},'#instrument-train-message'));
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
