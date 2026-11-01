import { randomUUID } from 'node:crypto';
import type { SupabaseClient } from '@supabase/supabase-js';
import { candidate,emptyStats,observe,qualifies,summarize } from '../lib/math';
import type { Dataset,Feature,Job,Work } from '../lib/types';
import { matchPattern } from '../services/patternMatcher';

const BATCH=16;
export async function optimizerTick(db:SupabaseClient,job:Job,token:string,deadline=Date.now()+40000) {
  const found=await db.from('market_datasets').select('*').eq('id',job.dataset_id).eq('user_id',job.user_id).single();
  if(found.error||!found.data)throw new Error('Dataset unavailable');
  const dataset=found.data as Dataset;
  let work:Work={...job.work};
  const commit=async(status:string,result:Record<string,unknown>|null=null,consume=false)=>{
    const {error}=await db.rpc('commit_optimizer_work',{p_id:job.id,p_token:token,p_work:work,p_status:status,p_result:result,p_consume_holdout:consume});
    if(error)throw new Error('Optimizer checkpoint rejected');
    return {job:job.id,status,stage:work.stage,trial:work.trial};
  };
  if(dataset.status!=='ready'){work.message='Dataset is not ready; ingestion must complete.';return commit('blocked');}
  if(work.trial>=job.max_trials){work.message='Development budget exhausted. Await new data or a separately reviewed research campaign; target is not proven.';return commit('waiting_new_data');}
  if(work.stage==='certification'&&dataset.holdout_run_id!==work.run_id){work.message='Final holdout was already consumed by another frozen run.';return commit('blocked');}
  if(work.stage==='certification'&&!dataset.source_verified){work.message='Dataset provenance approval was revoked; certification is blocked.';return commit('blocked');}
  const parameters=work.parameters||candidate(work.trial),stats=work.stats||emptyStats();
  work={...work,parameters,stats,run_id:work.run_id||randomUUID()};
  let query=db.from('historical_features').select('*').eq('dataset_id',dataset.id).gt('id',work.cursor||0).order('id').limit(BATCH);
  query=work.stage==='validation'?query.gt('observed_at',dataset.train_end).lt('outcome_at',dataset.validation_end):query.gt('observed_at',dataset.validation_end).lte('outcome_at',dataset.last_at);
  const {data,error}=await query;
  if(error)throw new Error('Evaluation data read failed');
  const points=(data||[]) as Feature[];
  let processed=0;
  for(const point of points) {
    if(Date.now()>deadline)break;
    work.cursor=point.id;processed++;
    // A deterministic single opportunity per timestamp, not a whole option chain.
    if(point.observed_at===stats.lastTime)continue;
    if(stats.lastOutcome&&Date.parse(point.observed_at)<Date.parse(stats.lastOutcome))continue;
    stats.lastTime=point.observed_at;
    stats.lastOutcome=point.outcome_at;
    const match=await matchPattern(db,dataset,point,parameters);
    observe(stats,match.probability,point.net_return,dataset.training_win_rate,match.accepted,point.regime,parameters.riskFraction,point.cost_return);
  }
  if(processed<points.length||points.length===BATCH)return commit('running');
  const passed=qualifies(stats);
  const result={id:work.run_id,trial:work.trial,stage:work.stage,parameters,metrics:{...summarize(stats),target:0.75,protocol:'Chronological, frozen training reference pool; validation is development data; one final holdout use',source_verified:dataset.source_verified},qualified:passed&&work.stage==='certification'&&dataset.source_verified};
  if(work.stage==='validation') {
    if(passed) {
      if(!dataset.source_verified){work.message='Promising development metrics, but uploaded data provenance needs operator approval before certification.';return commit('blocked',result);}
      if(dataset.holdout_run_id){work.message='Use fresh unseen data; this dataset final holdout has already been spent.';return commit('blocked',result);}
      // Freeze the candidate BEFORE touching final outcomes. Atomic SQL lock is single-use.
      work={trial:work.trial,stage:'certification',parameters,run_id:randomUUID(),cursor:null,stats:emptyStats()};
      return commit('running',result,true);
    }
    work={trial:work.trial+1,stage:'validation',cursor:null,stats:emptyStats()};
    return commit(work.trial>=job.max_trials?'waiting_new_data':'running',result);
  }
  work.message=passed?'Target passed on this frozen historical experiment, not a guarantee of future performance.':'Final certification failed. Do not retune against this holdout; await fresh independent data.';
  return commit(passed?'qualified':'blocked',result);
}
