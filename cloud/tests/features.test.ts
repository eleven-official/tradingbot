import { it,expect } from 'vitest';
import { causalFeature } from '../services/features';
const bars=Array.from({length:21},(_,i)=>({observed_at:new Date(Date.UTC(2020,0,i+1)).toISOString(),open:100+i,close:101+i,high:102+i,low:99+i,volume:1000}));
it('builds bounded causal12 features from completed bars',()=>{const f=causalFeature(bars);expect(f.embedding).toHaveLength(12);expect(f.embedding.every(v=>Number.isFinite(v)&&Math.abs(v)<=1)).toBe(true);expect(f.embedding.slice(8)).toEqual([0,0,0,0]);});
it('rejects incomplete and reversed windows',()=>{expect(()=>causalFeature(bars.slice(1))).toThrow();expect(()=>causalFeature([...bars].reverse())).toThrow();});
it('rejects invalid timestamps and nonfinite prices',()=>{expect(()=>causalFeature(bars.map((b,i)=>i===0?{...b,observed_at:'invalid'}:b))).toThrow();expect(()=>causalFeature(bars.map((b,i)=>i===0?{...b,close:Infinity}:b))).toThrow();});
