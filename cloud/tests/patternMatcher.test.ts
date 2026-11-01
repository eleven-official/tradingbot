import { describe,it,expect,vi } from 'vitest';
import type { SupabaseClient } from '@supabase/supabase-js';
import type { Dataset,Feature } from '../lib/types';
import { candidate } from '../lib/math';
import { matchPattern,rerank,vector } from '../services/patternMatcher';
const point=(id:number,date:string):Feature=>({id,observed_at:'2000-01-01T00:00:00Z',outcome_at:date,embedding:Array(12).fill(0),regime:'up',net_return:.1,cost_return:.001,contract_key:''});
describe('historical matching',()=>{
  it('rejects malformed vectors and weights',()=>{expect(()=>vector('[0]')).toThrow();expect(()=>vector(Array(12).fill(NaN))).toThrow();expect(()=>rerank(Array(12).fill(0),[],{...candidate(0),weights:[-1]})).toThrow();});
  it('deduplicates same-day option outcomes',()=>{const rows=[point(1,'2000-01-02T12:00:00Z'),point(2,'2000-01-02T13:00:00Z')];expect(rerank(Array(12).fill(0),rows,candidate(0)).neighbors).toBe(1);});
  it('abstains with no historical evidence',()=>{expect(rerank(Array(12).fill(0),[],candidate(0)).accepted).toBe(false);});
  it('accepts a sufficiently supported close analogue set',()=>{const rows=Array.from({length:40},(_,i)=>point(i,new Date(Date.UTC(2000,0,i+2)).toISOString()));expect(rerank(Array(12).fill(0),rows,candidate(0)).accepted).toBe(true);});
  it('rejects outcome leakage returned by the database',async()=>{const db={rpc:vi.fn().mockResolvedValue({data:[point(1,'2020-01-02T00:00:00Z')]})} as unknown as SupabaseClient;await expect(matchPattern(db,{id:'d',train_end:'2020-01-01T00:00:00Z'} as Dataset,{embedding:Array(12).fill(0),observed_at:'2021-01-01T00:00:00Z',contract_key:''},candidate(0))).rejects.toThrow('leakage');});
  it('blocks unverified pretrade sources before database access',async()=>{await expect(matchPattern({} as SupabaseClient,{train_end:'2000-01-01',source_verified:false} as Dataset,{embedding:Array(12).fill(0),observed_at:'2021-01-01',contract_key:''},candidate(0),'pretrade')).rejects.toThrow('provenance');});
});
