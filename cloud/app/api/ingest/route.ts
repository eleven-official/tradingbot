import { z } from 'zod';
import { operator } from '../../../lib/operator';
import { sameOrigin,failure } from '../../../lib/http';
export const runtime='nodejs';
const option=z.object({delta:z.number().min(-1).max(1),iv:z.number().positive().max(10),dte:z.number().min(0).max(730),moneyness:z.number().positive().max(10),entry_ask:z.number().positive(),exit_bid:z.number().nonnegative()}).strict();
const point=z.object({observed_at:z.string().datetime({offset:true}),outcome_at:z.string().datetime({offset:true}),embedding:z.array(z.number().finite().min(-1).max(1)).length(12),
  regime:z.enum(['up','down','range','stress']),net_return:z.number().finite().min(-1).max(10),cost_return:z.number().finite().min(0).max(2),contract_key:z.string().max(32).default(''),option_context:option.optional()}).strict();
const schema=z.object({dataset_id:z.string().uuid(),features:z.array(point).max(500),finish:z.boolean().default(false)}).strict();
export async function POST(request:Request) {
  try{
    sameOrigin(request);const {db,user}=await operator(request);const parsed=schema.safeParse(await request.json());
    if(!parsed.success)throw new Error('INPUT:Invalid bounded causal12 feature batch.');
    const b=parsed.data;
    const selected=await db.from('market_datasets').select('*').eq('id',b.dataset_id).eq('user_id',user.id).single();
    if(selected.error||!selected.data)throw new Error('FORBIDDEN');const dataset=selected.data;
    for(const feature of b.features){
      if(Date.parse(feature.outcome_at)<=Date.parse(feature.observed_at)||Date.parse(feature.outcome_at)>=Date.now())throw new Error('INPUT:Every label must be observed after its signal and before now.');
      if(dataset.asset_kind==='option'){
        const context=feature.option_context;
        if(!context||!new RegExp('^'+dataset.symbol+'[0-9]{6}[CP][0-9]{8}$').test(feature.contract_key))throw new Error('INPUT:Options need actual OCC contract and historical Greeks, DTE, moneyness and entry/exit quotes.');
        feature.embedding.splice(8,4,context.delta,Math.tanh(Math.log(context.moneyness)/0.1),Math.tanh(context.dte/60),Math.tanh(context.iv));
        feature.cost_return=2*dataset.option_commission/(context.entry_ask*100);
        feature.net_return=context.exit_bid/context.entry_ask-1-feature.cost_return;
        if(feature.cost_return>2||feature.net_return< -1||feature.net_return>10)throw new Error('INPUT:Option outcome is outside supported cost/return bounds.');
      }else if(feature.contract_key||feature.option_context)throw new Error('INPUT:Stock datasets cannot contain option labels.');
    }
    const result=await db.rpc('append_uploaded_features',{p_dataset:b.dataset_id,p_user:user.id,p_features:b.features,p_finish:b.finish});
    if(result.error)throw new Error('INPUT:Upload failed ordering, coverage or sealing checks. Keep batches chronological; source remains unverified until operator audit.');
    return Response.json({accepted:b.features.length,sealed:b.finish,source_verified:false});
  }catch(error){return failure(error);}
}
