import { REGIMES, type Parameters, type Stats, type Regime } from './types';
export function wilsonLower(wins:number,total:number,z=1.96):number {
  if(!Number.isInteger(total)||!Number.isInteger(wins)||total<=0||wins<0||wins>total)return 0;
  const p=wins/total, a=z*z/total;
  return (p+a/2-z*Math.sqrt(p*(1-p)/total+a/(4*total)))/(1+a);
}
export function emptyStats():Stats {
  return {examples:0,trades:0,wins:0,sum:0,stressSum:0,wealth:1,peak:1,maxDrawdown:0,brier:0,baselineBrier:0,
    regimes:{up:{trades:0,wins:0,net:0},down:{trades:0,wins:0,net:0},range:{trades:0,wins:0,net:0},stress:{trades:0,wins:0,net:0}}};
}
export function observe(s:Stats, probability:number, outcome:number, baseline:number, traded:boolean, regime:Regime, fraction:number,cost=0):void {
  if(![probability,outcome,baseline,fraction,cost].every(Number.isFinite))throw new Error('Nonfinite metric');
  if(probability<0||probability>1||baseline<0||baseline>1||fraction<0||fraction>1||cost<0||outcome< -1||!REGIMES.includes(regime))throw new Error('Invalid metric bounds');
  s.examples++; const won=outcome>0; s.brier+=(probability-Number(won))**2; s.baselineBrier+=(baseline-Number(won))**2;
  if(!traded)return;
  s.trades++;s.wins+=Number(won);s.sum+=outcome;s.stressSum+=outcome-cost;
  s.wealth*=Math.max(0,1+fraction*outcome);s.peak=Math.max(s.peak,s.wealth);s.maxDrawdown=Math.max(s.maxDrawdown,1-s.wealth/s.peak);
  const cell=s.regimes[regime];cell.trades++;cell.wins+=Number(won);cell.net+=outcome;
}
export function summarize(s:Stats) {
  return {examples:s.examples,trades:s.trades,win_rate:s.trades?s.wins/s.trades:null,
    win_rate_lower_95:wilsonLower(s.wins,s.trades), net_return:s.wealth-1,stress_sum:s.stressSum,expectancy:s.trades?s.sum/s.trades:null,
    max_drawdown:s.maxDrawdown,brier:s.examples?s.brier/s.examples:null,baseline_brier:s.examples?s.baselineBrier/s.examples:null,
    regimes:Object.fromEntries(REGIMES.map(name=>[name,{...s.regimes[name],lower_95:wilsonLower(s.regimes[name].wins,s.regimes[name].trades)}]))};
}
export function qualifies(s:Stats):boolean {
  return s.examples>=400&&s.trades>=400&&wilsonLower(s.wins,s.trades)>=0.75&&s.wealth>1&&s.sum>0&&s.stressSum>0&&s.maxDrawdown<=0.10&&s.brier<s.baselineBrier&&
    REGIMES.every(r=>s.regimes[r].trades>=100&&wilsonLower(s.regimes[r].wins,s.regimes[r].trades)>=0.75&&s.regimes[r].net>0);
}
// Predeclared bounded development search, not test-driven parameter selection.
export function candidate(trial:number):Parameters {
  if(!Number.isInteger(trial)||trial<0||trial>511)throw new Error('Invalid trial');
  const weights=Array.from({length:12},(_,i)=>1+(((trial*17+i*13)%5)-2)*0.15);
  return {k:[31,61,101][trial%3],confidence:[0.75,0.8,0.85][Math.floor(trial/3)%3],
    maxDistance:[0.6,0.9,1.2][Math.floor(trial/9)%3],riskFraction:[0.05,0.1][Math.floor(trial/27)%2],weights};
}
