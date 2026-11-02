import type { SupabaseClient } from '@supabase/supabase-js';
import type { Dataset, Feature, Parameters } from '../lib/types';
import { wilsonLower } from '../lib/math';
export function vector(value:string|number[]):number[] {
  const result=typeof value==='string'?JSON.parse(value):value;
  if(!Array.isArray(result)||result.length!==12||!result.every(v=>typeof v==='number'&&Number.isFinite(v)&&Math.abs(v)<=1))throw new Error('Invalid causal12 vector');
  return result;
}
export function rerank(query:number[],rows:Feature[],parameters:Parameters) {
  vector(query);
  if(!Number.isInteger(parameters.k)||parameters.k<1||parameters.k>256)throw new Error('Invalid neighbor count');
  if(parameters.weights.length!==12||parameters.weights.some(w=>!Number.isFinite(w)||w<=0))throw new Error('Invalid metric weights');
  const unique=new Set<string>();
  const ranked=rows.map(row=>({...row,distance:Math.sqrt(vector(row.embedding).reduce((sum,v,i)=>sum+parameters.weights[i]*(v-query[i])**2,0)/parameters.weights.reduce((a,b)=>a+b,0))})).sort((a,b)=>a.distance-b.distance||a.id-b.id);
  // Multiple option strikes on one outcome date are not independent trials.
  const chosen=ranked.filter(row=>{const date=new Date(row.outcome_at).toISOString().slice(0,10);if(unique.has(date))return false;unique.add(date);return true;}).slice(0,parameters.k);
  const wins=chosen.filter(row=>row.net_return-row.cost_return>0).length;
  // Two causal estimates agree or the call goes soft: the Laplace-smoothed win
  // share and the distance-softened share, where a close analogue outweighs a
  // far one. Refusal estimates stay separate; the Wilson lower bound below
  // still counts hard wins only, so acceptance gets no softer than before.
  const countShare=(wins+1)/(chosen.length+2);
  const openers=chosen.map(row=>1/(1+row.distance));
  const openerSum=openers.reduce((a,b)=>a+b,0);
  const openWins=openers.reduce((sum,w,i)=>sum+w*Number(chosen[i].net_return-chosen[i].cost_return>0),0);
  const softShare=openerSum>0?openWins/openerSum:0.5;
  const probability=chosen.length?(countShare+softShare)/2:0.5;
  const lower=wilsonLower(wins,chosen.length);
  const distance=chosen.length?chosen.reduce((sum,row)=>sum+row.distance,0)/chosen.length:Infinity;
  return {probability,lower,distance,neighbors:chosen.length,accepted:chosen.length>=parameters.k&&lower>=parameters.confidence&&distance<=parameters.maxDistance,
    analogues:chosen.slice(0,5).map(row=>({observed_at:row.observed_at,outcome_at:row.outcome_at,distance:row.distance,net_return:row.net_return}))};
}
export async function matchPattern(db:SupabaseClient,dataset:Dataset,point:Pick<Feature,'observed_at'|'embedding'|'contract_key'|'option_context'>,parameters:Parameters,mode:'evaluation'|'pretrade'='evaluation') {
  const query=vector(point.embedding);
  if(!Number.isFinite(Date.parse(point.observed_at))||!Number.isFinite(Date.parse(dataset.train_end)))throw new Error('Invalid signal/reference timestamp');
  if(mode==='pretrade') {
    if(!dataset.source_verified||dataset.status!=='ready')throw new Error('Dataset provenance not approved');
    if(Date.parse(point.observed_at)<Date.parse(dataset.last_at))throw new Error('Readiness outcomes are later than this signal');
    if(dataset.asset_kind==='option'&&(!point.contract_key||!point.option_context))throw new Error('Options need actual contract and Greek/moneyness context');
  }
  const {data,error}=await db.rpc('match_historical_patterns',{p_dataset:dataset.id,p_as_of:point.observed_at,p_reference_end:dataset.train_end,p_embedding:JSON.stringify(query),p_count:256});
  if(error)throw new Error('Historical vector query failed');
  const rows=(data||[]) as Feature[];
  // Independently fail closed if a server/query regression exposes later labels.
  if(rows.some(row=>!Number.isFinite(Date.parse(row.outcome_at))||!Number.isFinite(Date.parse(row.observed_at))||Date.parse(row.observed_at)>=Date.parse(row.outcome_at)||Date.parse(row.outcome_at)>=Math.min(Date.parse(point.observed_at),Date.parse(dataset.train_end))))throw new Error('Historical label leakage detected');
  return rerank(query,rows,parameters);
}
