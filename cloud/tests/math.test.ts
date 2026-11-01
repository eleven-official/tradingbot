import { describe,it,expect } from 'vitest';
import { candidate,emptyStats,observe,qualifies,wilsonLower } from '../lib/math';
import { REGIMES } from '../lib/types';
describe('qualification math',()=>{
  it('rejects absent and invalid sample sizes',()=>{expect(wilsonLower(0,0)).toBe(0);expect(wilsonLower(10,9)).toBe(0);expect(wilsonLower(4,4.1)).toBe(0);});
  it('does not call 75 wins in 100 a proven 75% edge',()=>{expect(wilsonLower(75,100)).toBeLessThan(.75);expect(wilsonLower(95,100)).toBeGreaterThan(.75);});
  it('requires sufficient evidence in every regime and cost stress',()=>{
    const s=emptyStats();expect(qualifies(s)).toBe(false);
    REGIMES.forEach(r=>{for(let i=0;i<110;i++)observe(s,.95,.02,.5,true,r,.1,.001);});
    expect(qualifies(s)).toBe(true);s.stressSum=-1;expect(qualifies(s)).toBe(false);s.stressSum=1;s.regimes.stress.trades=99;expect(qualifies(s)).toBe(false);
  });
  it('tracks actual losses and drawdown',()=>{const s=emptyStats();observe(s,.9,-.5,.5,true,'down',.5,.01);expect(s.wealth).toBe(.75);expect(s.maxDrawdown).toBe(.25);expect(s.wins).toBe(0);});
  it('does not turn abstentions into trades',()=>{const s=emptyStats();observe(s,.4,.1,.5,false,'up',.1);expect(s.examples).toBe(1);expect(s.trades).toBe(0);expect(s.wealth).toBe(1);});
  it('predeclares deterministic bounded candidates',()=>{expect(candidate(2)).toEqual(candidate(2));expect(candidate(2).weights).toHaveLength(12);expect(()=>candidate(512)).toThrow();});
  it('rejects malformed cost and risk inputs',()=>{expect(()=>observe(emptyStats(),.5,.1,.5,true,'up',.1,NaN)).toThrow();expect(()=>observe(emptyStats(),.5,.1,.5,true,'up',2)).toThrow();});
});
