'use strict';
(()=>{
  let preview=null,cancelTarget=null,busy=false,canWrite=false,canRead=false;
  const terminal=new Set(['closed','canceled','expired','rejected']);
  const current=()=>location.hash==='#real-market';
  function controls(){
    $('#real-order-fields').disabled=busy||!canWrite;
    $('#real-orders-refresh').disabled=busy||!canRead;
    const fresh=preview&&Date.now()/1000<preview.expires_at;
    $('#real-order-submit').disabled=busy||!current()||!canWrite||!fresh||$('#real-order-confirmation').value!=='PLACE REAL ORDER';
    $('#real-order-cancel').disabled=busy||!current()||!canRead||!cancelTarget||$('#real-cancel-confirmation').value!=='CANCEL REAL ORDER';
    if(preview)$('#real-preview-expiry').textContent=fresh?`Preview expires in ${Math.max(0,Math.ceil(preview.expires_at-Date.now()/1000))} seconds. Funds and venue limits are checked again before submission.`:'Preview expired. Request and review a new preview.';
  }
  function clearPreview(){preview=null;$('#real-order-preview').hidden=true;$('#real-order-confirmation').value='';controls();}
  async function perform(task,target){if(busy)return;busy=true;controls();try{await task();}catch(error){message(target,error.message,true);}finally{busy=false;controls();}}
  window.addEventListener('loki-real-status',event=>{
    const data=event.detail;canWrite=Boolean(data.order_submission_available);canRead=Boolean(data.ready_to_connect&&data.exchange==='kraken');
    $('#real-order-availability').textContent=canWrite?'Host enabled · confirmation required':'Manual orders disabled';
    if(!canWrite)clearPreview();controls();
  });
  function showPreview(data){
    window.dispatchEvent(new Event('loki-real-authenticated'));preview=data;$('#real-order-confirmation').value='';const order=data.request,quote=data.preview;
    $('#real-preview-summary').replaceChildren(element('h3',`${order.side.toUpperCase()} ${number(order.quantity,8)} ${order.symbol} · GTC limit`),inlineMetrics([['Limit price',number(order.limit_price,8)+' USD'],['Order notional',number(Number(quote.estimated_notional_usd))+' USD'],['Estimated fee buffer',number(Number(quote.fee_buffer_usd))+' USD']]));
    $('#real-preview-summary').append(element('p',`Observed bid ${quote.bid} / ask ${quote.ask} USD. Venue timestamp ${quote.venue_timestamp==null?'unavailable':new Date(quote.venue_timestamp).toISOString()}.`,'caption'),bulletList(quote.notes),detailsJSON(data,'Inspect exact order preview'));
    $('#real-order-preview').hidden=false;controls();
  }
  async function history(){
    const data=await request('/api/fusion/real/orders',undefined,true);const rows=data.orders;
    $('#real-orders').replaceChildren(rows.length?table(['Created / UTC','Order','Local state','Venue status / filled','Action'],rows.map(row=>{
      const buttons=element('div',null,'button-row');
      if(row.state!=='prepared'&&!terminal.has(row.state)){
        const refresh=element('button','Refresh venue status','button secondary sim-actions');refresh.type='button';refresh.addEventListener('click',()=>perform(async()=>{const next=await request(`/api/fusion/real/orders/${row.id}/reconcile`,{},true);message('#real-journal-message',next.message);await history();},'#real-journal-message'));buttons.append(refresh);
      }
      if(row.state==='submitted'&&row.order?.id){const cancel=element('button','Review cancellation','button secondary sim-actions');cancel.type='button';cancel.addEventListener('click',()=>{cancelTarget=row;$('#real-cancel-confirmation').value='';$('#real-cancel-panel').hidden=false;$('#real-cancel-summary').textContent=`Cancel venue order ${row.order.id}: ${row.request.side} ${row.request.quantity} ${row.request.symbol} at ${row.request.limit_price} USD. Filled units reported: ${row.order.filled??'unknown'}.`;controls();});buttons.append(cancel);}
      const inspect=element('button','Details','button secondary sim-actions');inspect.type='button';inspect.addEventListener('click',()=>exportJSON(row,`loki-real-order-${row.id}.json`));buttons.append(inspect);
      return[new Date(row.created_at*1000).toISOString().replace('T',' ').slice(0,19),`${row.request.side} ${row.request.quantity} ${row.request.symbol} @ ${row.request.limit_price}`,human(row.state),`${row.order?.status||'Unknown'} / ${row.order?.filled??'Unknown'}`,buttons];
    })):element('p','No order previews recorded for this account key.','muted'));
  }
  $('#real-order-form').addEventListener('input',clearPreview);
  $('#real-order-form').addEventListener('submit',event=>{event.preventDefault();if(!canWrite||!current())return;const form=new FormData(event.target),payload={symbol:form.get('symbol'),side:form.get('side'),quantity:Number(form.get('quantity')),limit_price:Number(form.get('limit_price'))};perform(async()=>{clearPreview();const data=await request('/api/fusion/real/orders/preview',payload,true);showPreview(data);message('#real-order-message','Preview ready. No real order has been submitted.');},'#real-order-message');});
  $('#real-order-confirmation').addEventListener('input',controls);
  $('#real-cancel-confirmation').addEventListener('input',controls);
  $('#real-order-confirm-form').addEventListener('submit',event=>{event.preventDefault();controls();if($('#real-order-submit').disabled)return;const identifier=preview.id,confirmation=$('#real-order-confirmation').value;perform(async()=>{const data=await request('/api/fusion/real/orders/submit',{identifier,confirmation},true);clearPreview();message('#real-order-message',`${human(data.state)}. ${data.message}`);await history();},'#real-order-message');});
  $('#real-orders-refresh').addEventListener('click',()=>perform(history,'#real-journal-message'));
  $('#real-order-cancel-form').addEventListener('submit',event=>{event.preventDefault();controls();if($('#real-order-cancel').disabled)return;const identifier=cancelTarget.id,confirmation=$('#real-cancel-confirmation').value;perform(async()=>{const data=await request('/api/fusion/real/orders/cancel',{identifier,confirmation},true);cancelTarget=null;$('#real-cancel-panel').hidden=true;$('#real-cancel-confirmation').value='';message('#real-journal-message',`${human(data.state)}. ${data.message}`);await history();},'#real-journal-message');});
  window.addEventListener('hashchange',()=>{if(!current()){clearPreview();cancelTarget=null;$('#real-cancel-panel').hidden=true;}controls();});
  setInterval(controls,1000);controls();
})();
