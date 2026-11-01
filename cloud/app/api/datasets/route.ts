import { z } from 'zod';
import { operator } from '../../../lib/operator';
import { sameOrigin,failure } from '../../../lib/http';
export const runtime='nodejs';
const bodySchema=z.object({symbol:z.string().regex(/^[A-Z][A-Z0-9.]{0,11}$/),asset_kind:z.enum(['stock','option']).default('stock'),
  timeframe:z.enum(['1d','15m','5m']).default('1d'),years:z.union([z.literal(10),z.literal(15),z.literal(20)]),source:z.enum(['alpaca','upload'])}).strict();
export async function POST(request:Request) {
  try{
    sameOrigin(request);const {db,user}=await operator(request);
    const parsed=bodySchema.safeParse(await request.json());if(!parsed.success)throw new Error('INPUT:Choose an instrument, 10/15/20 years and an explicit provider.');
    const b=parsed.data;
    if(b.source==='alpaca'&&(b.asset_kind!=='stock'||b.timeframe!=='1d'))throw new Error('INPUT:Licensed option/intraday history must be uploaded; daily stock data is not a substitute.');
    const count=await db.from('market_datasets').select('id',{count:'exact',head:true}).eq('user_id',user.id);
    if(count.error)throw count.error;if((count.count||0)>=20)throw new Error('INPUT:Dataset quota reached; contact the operator.');
    const result=await db.from('market_datasets').insert({user_id:user.id,symbol:b.symbol,asset_kind:b.asset_kind,timeframe:b.timeframe,
      requested_years:b.years,source:b.source,source_verified:b.source==='alpaca'}).select('id,status').single();
    if(result.error)throw result.error;
    return Response.json(result.data,{status:201});
  }catch(error){return failure(error);}
}
