import { beforeEach,it,expect,vi } from 'vitest';
import type { SupabaseClient } from '@supabase/supabase-js';
import type { Dataset,Job,Stats } from '../lib/types';
import { REGIMES } from '../lib/types';
import { candidate,emptyStats,observe } from '../lib/math';
vi.mock('../services/patternMatcher',()=>({matchPattern:vi.fn().mockResolvedValue({probability:.95,accepted:true})}));
import { optimizerTick } from '../services/optimizer';
import { matchPattern } from '../services/patternMatcher';
const dataset={id:'dataset',user_id:'owner',status:'ready',source_verified:true,train_end:'2010-01-01',validation_end:'2015-01-01',last_at:'2020-01-01',training_win_rate:.5,holdout_run_id:null} as Dataset;
const job=():Job=>({id:'job',user_id:'owner',dataset_id:'dataset',max_trials:2,status:'running',work:{trial:0,stage:'validation'}});
function passing():Stats{const s=emptyStats();REGIMES.forEach(r=>{for(let i=0;i<110;i++)observe(s,.95,.02,.5,true,r,.1,.001);});return s;}
function database(d:Dataset=dataset,points:unknown[]=[]) {
  const rpc=vi.fn().mockResolvedValue({error:null});
  const features={select:vi.fn(),eq:vi.fn(),gt:vi.fn(),lt:vi.fn(),lte:vi.fn(),order:vi.fn(),limit:vi.fn(),then:undefined} as Record<string,unknown>;
  for(const key of Object.keys(features))if(key!=='then')features[key]=vi.fn().mockReturnValue(features);
  features.then=(resolve:(v:unknown)=>void)=>Promise.resolve({data:points,error:null}).then(resolve);
  const from=vi.fn((table:string)=>table==='market_datasets'?{select:()=>({eq:()=>({eq:()=>({single:async()=>({data:d,error:null})})})})}:features);
  return {db:{from,rpc} as unknown as SupabaseClient,rpc,features,from};
}
beforeEach(()=>vi.clearAllMocks());
it('freezes the successful development candidate and consumes holdout atomically',async()=>{
  const j=job();j.work.stats=passing();const {db,rpc}=database();await optimizerTick(db,j,'lease');const args=rpc.mock.calls[0][1];
  expect(args.p_consume_holdout).toBe(true);expect(args.p_work.stage).toBe('certification');expect(args.p_work.parameters).toEqual(candidate(0));expect(args.p_work.stats.examples).toBe(0);expect(args.p_result.qualified).toBe(false);
});
it('never reads evaluation examples from a final holdout locked by another run',async()=>{
  const j=job();j.work={trial:0,stage:'certification',run_id:'mine'};const {db,from,rpc}=database({...dataset,holdout_run_id:'other'});await optimizerTick(db,j,'lease');expect(from).toHaveBeenCalledTimes(1);expect(rpc.mock.calls[0][1].p_status).toBe('blocked');
});
it('blocks unverified upload certification despite passing development metrics',async()=>{
  const j=job();j.work.stats=passing();const {db,rpc}=database({...dataset,source_verified:false});await optimizerTick(db,j,'lease');expect(rpc.mock.calls[0][1].p_status).toBe('blocked');expect(rpc.mock.calls[0][1].p_consume_holdout).toBe(false);
});
it('blocks certification when provenance approval has been revoked',async()=>{
  const j=job();j.work={trial:0,stage:'certification',run_id:'mine'};const {db,from,rpc}=database({...dataset,holdout_run_id:'mine',source_verified:false});await optimizerTick(db,j,'lease');expect(from).toHaveBeenCalledTimes(1);expect(rpc.mock.calls[0][1].p_status).toBe('blocked');
});
it('advances failed development trials within a finite compute budget',async()=>{
  const {db,rpc}=database();await optimizerTick(db,job(),'lease');expect(rpc.mock.calls[0][1].p_work.trial).toBe(1);expect(rpc.mock.calls[0][1].p_status).toBe('running');
});
it('does not keep retuning against failed certification',async()=>{
  const j=job();j.work={trial:0,stage:'certification',run_id:'mine',parameters:candidate(0)};const {db,rpc}=database({...dataset,holdout_run_id:'mine'});await optimizerTick(db,j,'lease');expect(rpc.mock.calls[0][1].p_status).toBe('blocked');expect(rpc.mock.calls[0][1].p_work.trial).toBe(0);
});
it('propagates rejected checkpoints rather than reporting committed progress',async()=>{
  const {db,rpc}=database();rpc.mockResolvedValue({error:{message:'stale lease'}} as never);await expect(optimizerTick(db,job(),'stale')).rejects.toThrow('checkpoint rejected');
});
it('excludes overlapping label intervals from simulated execution',async()=>{
  const j=job();const {db,rpc}=database(dataset,[{id:1,observed_at:'2012-01-01',outcome_at:'2012-01-05',net_return:.1,cost_return:.01,regime:'up'},{id:2,observed_at:'2012-01-02',outcome_at:'2012-01-06',net_return:.1,cost_return:.01,regime:'up'}]);await optimizerTick(db,j,'lease');expect(matchPattern).toHaveBeenCalledTimes(1);expect(rpc.mock.calls[0][1].p_result.metrics.examples).toBe(1);
});
