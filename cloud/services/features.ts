import type { Bar, Regime } from '../lib/types';
export function causalFeature(window:Bar[]):{embedding:number[];regime:Regime} {
  if(window.length!==21)throw new Error('Need 21 completed bars');
  if(window.some((b,i)=>![b.open,b.high,b.low,b.close,b.volume,Date.parse(b.observed_at)].every(Number.isFinite)||b.low<=0||b.open<b.low||b.close<b.low||b.high<Math.max(b.open,b.close)||b.volume<0||(i>0&&Date.parse(b.observed_at)<=Date.parse(window[i-1].observed_at))))throw new Error('Invalid OHLCV window');
  const returns=window.slice(1).map((b,i)=>Math.log(b.close/window[i].close));
  const mean=(a:number[])=>a.reduce((x,y)=>x+y,0)/a.length;
  const avg=mean(returns),vol=Math.sqrt(mean(returns.map(r=>(r-avg)**2)));
  const b=window[20],high=Math.max(...window.map(b=>b.high)),low=Math.min(...window.map(b=>b.low)),volume=mean(window.map(b=>b.volume));
  const momentum=Math.log(b.close/window[0].close);
  const embedding=[Math.tanh(returns[19]/0.01),Math.tanh(mean(returns.slice(-5))/0.01),Math.tanh(avg/0.01),Math.tanh(vol/0.02),
    Math.tanh((high-low)/b.close/0.04),Math.tanh((b.close-b.open)/b.open/0.02),Math.tanh(volume?b.volume/volume-1:0),high>low?2*(b.close-low)/(high-low)-1:0,0,0,0,0];
  const regime:Regime=vol>0.03?'stress':Math.abs(momentum)<0.01?'range':momentum>0?'up':'down';
  return {embedding,regime};
}
