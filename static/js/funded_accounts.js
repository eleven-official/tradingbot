'use strict';
(() => {
  const el=id=>document.getElementById(id),root=el('ai-lucid-controls');
  if(!root)return;
  let state=null,busy=false,revision=0;
  const text=(tag,value)=>{const n=document.createElement(tag);n.textContent=value;return n;};
  const format=v=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString(undefined,{maximumFractionDigits:2}):'Unavailable';
  function table(headers,rows){const wrap=text('div','');wrap.className='table-scroll';const t=document.createElement('table'),head=document.createElement('thead'),tr=document.createElement('tr'),body=document.createElement('tbody');headers.forEach(h=>tr.append(text('th',h)));head.append(tr);rows.forEach(row=>{const r=document.createElement('tr');row.forEach(v=>r.append(text('td',String(v??'Unavailable'))));body.append(r);});t.append(head,body);wrap.append(t);return wrap;}
  function render(){
    const linked=!!state?.connected;
    el('funded-status').textContent=linked?'Connected · account viewing':'Not connected to Loki';
    el('funded-account-controls').hidden=!linked;
    root.querySelectorAll('button,input,select').forEach(n=>n.disabled=busy);
    const details=el('funded-account-details');details.replaceChildren();
    if(!linked)return;
    const picker=el('funded-account-select'),selected=picker.value;picker.replaceChildren();
    state.accounts.forEach(a=>picker.append(new Option(`${a.name||'Account'} · ${a.id}${a.closed?' · closed':a.restricted?' · restricted':''}`,String(a.id))));
    if(state.accounts.some(a=>String(a.id)===selected))picker.value=selected;
    const id=Number(picker.value),account=state.accounts.find(a=>a.id===id);
    details.append(text('h3',account?.name||'Account'),text('p',`${state.environment.toUpperCase()} server · ${account?.closed?'Closed':account?.restricted?'Restricted':'Verified account'} · last refreshed ${new Date().toLocaleTimeString()}`));
    details.append(text('h4','Cash balances'));
    if(state.balances===null)details.append(text('p','Balances could not be read. Refresh to try again.'));
    else{const balances=state.balances.filter(b=>b.account_id===id);details.append(balances.length?table(['Currency ID','Cash','Realized P&L','Broker timestamp'],balances.map(b=>[b.currency_id,format(b.cash),format(b.realized_pnl),b.timestamp])):text('p','Tradovate returned no cash balances for this account.'));}
    details.append(text('h4','Open positions'));
    if(state.positions===null)details.append(text('p','Positions could not be read. This does not mean the account is flat.'));
    else{const positions=state.positions.filter(p=>p.account_id===id);details.append(positions.length?table(['Contract ID','Net contracts','Net price'],positions.map(p=>[p.contract_id,format(p.quantity),format(p.net_price)])):text('p','No open positions returned for this account.'));}
    if(state.messages?.length)details.append(text('p',state.messages.join(' ')));
    details.append(text('p',`Connection expires by ${new Date(state.expires_at*1000).toLocaleTimeString()}. Trading remains on your broker's platform.`));
  }
  async function api(path,body){
    const owner=window.LokiStorageOwner;
    if(!owner||owner==='guest')throw Error('Sign in to Loki first, then connect your funded account.');
    const r=await fetch('/api/account/funded'+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-Workspace-Owner':owner},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
    const data=await r.json();
    if(owner!==window.LokiStorageOwner)throw Error('Account changed. Reload this page.');
    if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'Connection could not be verified. Check the server and token.');
    return data;
  }
  async function load(path='',body){
    if(busy)return;busy=true;const current=++revision;render();el('funded-message').textContent='Reading your Tradovate account…';
    try{const next=await api(path,body);if(current!==revision)return;state=next;el('funded-message').textContent=state.connected?'Account verified. Select the account you want to view.':state.configured===false?'Direct API linking is not configured on this server. Use the TradersPost setup above.':'No direct connection. Choose a method above to get started.';}
    catch(e){state=null;el('funded-message').textContent=e.message;}
    finally{busy=false;render();}
  }
  el('funded-connect-form').addEventListener('submit',e=>{e.preventDefault();if(busy)return;const form=new FormData(e.target),body={environment:form.get('environment'),access_token:String(form.get('access_token')).trim()};e.target.elements.access_token.value='';void load('/connect',body);});
  el('funded-login-form')?.addEventListener('submit',e=>{e.preventDefault();if(busy)return;const f=e.target,form=new FormData(f);const body={environment:form.get('environment'),username:String(form.get('username')||'').trim(),password:String(form.get('password')||''),cid:Number(form.get('cid')),sec:String(form.get('sec')||'')};f.elements.password.value='';f.elements.sec.value='';void load('/login',body);});
  el('funded-refresh').addEventListener('click',()=>void load());
  el('funded-disconnect').addEventListener('click',()=>void load('/disconnect',{}));
  el('funded-account-select').addEventListener('change',render);
  const workspace=el('ai-trading'),tabs=[...document.querySelectorAll('[data-trading-lane]')];
  function selectLane(lane){
    tabs.forEach(b=>{const selected=b.dataset.tradingLane===lane;b.setAttribute('aria-pressed',String(selected));b.classList.toggle('primary',selected);b.classList.toggle('secondary',!selected);});
    workspace.querySelectorAll(':scope > section').forEach(section=>{const category=section.id==='ai-lucid-controls'?'funded':section.id==='ai-live-controls'?'live':'paper';section.hidden=category!==lane;});
    el('trading-lane-note').textContent={paper:'Practice uses simulated money. No broker connection needed.',live:'Connect Alpaca, set your limits, then start when ready. Requires the local launcher.',funded:'Connect your Tradovate account or open the guided TradersPost setup. Works on the hosted Loki website.'}[lane];
    if(lane==='funded')void load();
  }
  tabs.forEach(b=>b.addEventListener('click',()=>selectLane(b.dataset.tradingLane)));
  selectLane('paper');render();
})();
