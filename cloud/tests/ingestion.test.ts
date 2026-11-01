import { afterEach,it,expect,vi } from 'vitest';
import type { SupabaseClient } from '@supabase/supabase-js';
import type { Dataset } from '../lib/types';
import { ingestionTick } from '../services/ingestion';
const dataset:Dataset={id:'dataset',user_id:'owner',symbol:'SPY',source:'alpaca',source_verified:true,status:'ingesting',asset_kind:'stock',timeframe:'1d',requested_years:20,raw_count:0,feature_count:0,cursor:{phase:'fetch'},first_at:'',last_at:'',train_end:'',validation_end:'',training_win_rate:.5,fee_bps:10,slippage_bps:5,option_commission:.65,holdout_run_id:null};
afterEach(()=>{vi.unstubAllEnvs();vi.unstubAllGlobals();});
it('does not silently substitute stocks for option history',async()=>{
  const rpc=vi.fn().mockResolvedValue({error:null});await ingestionTick({rpc} as unknown as SupabaseClient,{...dataset,asset_kind:'option'},'lease');expect(rpc.mock.calls[0][1].p_patch.status).toBe('waiting_data');
});
it('waits for configured provider credentials',async()=>{
  vi.stubEnv('ALPACA_DATA_KEY','');vi.stubEnv('ALPACA_DATA_SECRET','');const rpc=vi.fn().mockResolvedValue({error:null});await ingestionTick({rpc} as unknown as SupabaseClient,dataset,'lease');expect(rpc.mock.calls[0][1].p_patch.status).toBe('waiting_data');
});
it('rejects incomplete multi-year provider coverage',async()=>{
  const rpc=vi.fn().mockImplementation((name:string)=>Promise.resolve(name==='summarize_market_bars'?{data:{count:300,first_at:'2025-01-01',last_at:'2026-01-01',max_gap_seconds:86400}}:{error:null}));await ingestionTick({rpc} as unknown as SupabaseClient,{...dataset,cursor:{phase:'initialize'}},'lease');expect(rpc.mock.calls[1][1].p_patch.status).toBe('waiting_data');
});
it('distinguishes entitlement rejection from usable history',async()=>{
  vi.stubEnv('ALPACA_DATA_KEY','test');vi.stubEnv('ALPACA_DATA_SECRET','test');vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('',{status:403})));
  const rpc=vi.fn().mockResolvedValue({error:null});await ingestionTick({rpc} as unknown as SupabaseClient,dataset,'lease');expect(rpc.mock.calls[0][1].p_patch.last_error).toContain('403');expect(rpc.mock.calls[0][1].p_bars).toEqual([]);
});
it('fails closed on an uncommitted ingestion checkpoint',async()=>{
  const rpc=vi.fn().mockResolvedValue({error:{message:'stale'}});await expect(ingestionTick({rpc} as unknown as SupabaseClient,{...dataset,asset_kind:'option'},'lease')).rejects.toThrow('checkpoint rejected');
});
