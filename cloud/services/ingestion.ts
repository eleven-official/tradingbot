import type { SupabaseClient } from '@supabase/supabase-js';
import { z } from 'zod';
import type { Bar, Dataset } from '../lib/types';
import { causalFeature } from './features';

const vendorBar=z.object({t:z.string(),o:z.number().positive().finite(),h:z.number().positive().finite(),l:z.number().positive().finite(),c:z.number().positive().finite(),v:z.number().nonnegative().finite()});
export async function ingestionTick(db:SupabaseClient,dataset:Dataset,token:string) {
  const checkpoint=async(patch:Record<string,unknown>,bars:Bar[]=[],features:Record<string,unknown>[]=[])=>{
    const {error}=await db.rpc('commit_dataset_work',{p_id:dataset.id,p_token:token,p_patch:patch,p_bars:bars,p_features:features});
    if(error)throw new Error('Ingestion checkpoint rejected');
    return {dataset:dataset.id,status:patch.status||dataset.status};
  };
  if(dataset.source!=='alpaca'||dataset.asset_kind!=='stock'||dataset.timeframe!=='1d')return checkpoint({status:'waiting_data',last_error:'Supply licensed contract-matched option/intraday feature history; no daily-stock substitute is used.'});
  if(dataset.cursor.phase==='fetch') {
    const key=process.env.ALPACA_DATA_KEY,secret=process.env.ALPACA_DATA_SECRET;
    if(!key||!secret)return checkpoint({status:'waiting_data',last_error:'Server market-data credentials are not configured.'});
    const today=new Date().toISOString().slice(0,10),start=new Date(Date.now()-dataset.requested_years*365.25*86400000).toISOString().slice(0,10);
    const url=new URL(`https://data.alpaca.markets/v2/stocks/${encodeURIComponent(dataset.symbol)}/bars`);
    Object.entries({start,end:today,timeframe:'1Day',feed:'iex',adjustment:'split',sort:'asc',limit:'10000'}).forEach(([k,v])=>url.searchParams.set(k,v));
    if(typeof dataset.cursor.page_token==='string')url.searchParams.set('page_token',dataset.cursor.page_token);
    const response=await fetch(url,{headers:{'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret},redirect:'error',signal:AbortSignal.timeout(15000),cache:'no-store'});
    if(!response.ok)return checkpoint({status:'waiting_data',last_error:`Market-data provider rejected the request (${response.status}); check entitlement, not just trading access.`});
    const body=z.object({bars:z.array(vendorBar).max(10000).nullable().optional(),next_page_token:z.string().max(2048).nullable().optional()}).parse(await response.json());
    const bars:Bar[]=(body.bars||[]).filter(b=>b.t.slice(0,10)<today).map(b=>({observed_at:b.t.slice(0,10)+'T23:59:59.000Z',open:b.o,high:b.h,low:b.l,close:b.c,volume:b.v}));
    const count=dataset.raw_count+bars.length,pages=Number(dataset.cursor.pages||0)+1;
    if(count>10000||pages>5||(body.next_page_token&&body.next_page_token===dataset.cursor.page_token))return checkpoint({status:'failed',last_error:'History pagination exceeded bounds or repeated a token.'});
    return checkpoint({raw_count:count,status:body.next_page_token?'ingesting':'featurizing',cursor:body.next_page_token?{phase:'fetch',pages,page_token:body.next_page_token}:{phase:'initialize'}},bars);
  }
  if(dataset.cursor.phase==='initialize') {
    const {data:summary,error}=await db.rpc('summarize_market_bars',{p_dataset:dataset.id});
    if(error||!summary)throw new Error('History summary unavailable');
    if(summary.count<dataset.requested_years*170||(Date.parse(summary.last_at)-Date.parse(summary.first_at))/31557600000<dataset.requested_years-0.2)
      return checkpoint({status:'waiting_data',last_error:`Provider returned only ${summary.count} bars; requested coverage is incomplete. Supply licensed longer history.`});
    if(summary.max_gap_seconds>7*86400)return checkpoint({status:'waiting_data',last_error:'Daily source has a gap longer than seven days; repair source history.'});
    return checkpoint({raw_count:summary.count,first_at:summary.first_at,last_at:summary.last_at,train_end:summary.train_end,
      validation_end:summary.validation_end,cursor:{phase:'features',index:20}});
  }
  const index=Number(dataset.cursor.index||20),end=Math.min(index+500,dataset.raw_count-1),features=[];
  const {data:raw,error}=await db.from('market_bars').select('observed_at,open,high,low,close,volume').eq('dataset_id',dataset.id).order('observed_at').range(index-20,end);
  if(error||!raw||raw.length!==end-index+21)throw new Error('Raw feature window incomplete');
  const all=raw as Bar[];
  const roundTrip=2*(dataset.fee_bps+dataset.slippage_bps)/10000;
  for(let i=20;i<all.length-1;i++) {
    const feature=causalFeature(all.slice(i-20,i+1)),next=all[i+1];
    features.push({...feature,observed_at:all[i].observed_at,outcome_at:next.observed_at,
      net_return:next.close/next.open-1-roundTrip,cost_return:roundTrip,contract_key:''});
  }
  const trainEnd=dataset.train_end;
  const done=end>=dataset.raw_count-1;
  const patch:Record<string,unknown>={status:done?'ready':'featurizing',feature_count:dataset.feature_count+features.length,cursor:{phase:'features',index:end}};
  if(done){
    const total=await db.from('historical_features').select('id',{count:'exact',head:true}).eq('dataset_id',dataset.id).lt('outcome_at',trainEnd);
    const wins=await db.from('historical_features').select('id',{count:'exact',head:true}).eq('dataset_id',dataset.id).lt('outcome_at',trainEnd).gt('net_return',0);
    if(total.error||wins.error||!total.count)throw new Error('Training baseline could not be verified');
    patch.training_win_rate=(wins.count||0)/total.count;
  }
  return checkpoint(patch,[],features);
}
