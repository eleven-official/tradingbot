import { z } from 'zod';
import { operator } from '../../../lib/operator';
import { sameOrigin,failure } from '../../../lib/http';
export const runtime='nodejs';
export async function POST(request:Request) {
  try{
    sameOrigin(request);const {db,user}=await operator(request);
    const parsed=z.object({dataset_id:z.string().uuid(),max_trials:z.number().int().min(1).max(512).default(128)}).strict().safeParse(await request.json());
    if(!parsed.success)throw new Error('INPUT:Invalid research budget or dataset.');
    const found=await db.from('market_datasets').select('id,status,holdout_run_id').eq('id',parsed.data.dataset_id).eq('user_id',user.id).single();
    if(found.error||!found.data)throw new Error('FORBIDDEN');
    if(found.data.status!=='ready'||found.data.holdout_run_id)throw new Error('INPUT:Dataset must be ready with an unconsumed final holdout.');
    const active=await db.from('ai_optimization_jobs').select('id',{count:'exact',head:true}).eq('user_id',user.id).in('status',['queued','running']);
    if(active.error)throw active.error;if((active.count||0)>=3)throw new Error('INPUT:At most three active campaigns per operator.');
    const result=await db.from('ai_optimization_jobs').insert({...parsed.data,user_id:user.id}).select('id,status').single();
    if(result.error)throw new Error('INPUT:A campaign already owns this dataset or storage is unavailable.');
    return Response.json(result.data,{status:201});
  }catch(error){return failure(error);}
}
export async function PATCH(request:Request) {
  try{
    sameOrigin(request);const {db,user}=await operator(request);
    const parsed=z.object({id:z.string().uuid(),action:z.enum(['pause','resume'])}).strict().safeParse(await request.json());
    if(!parsed.success)throw new Error('INPUT:Invalid campaign control.');
    const b=parsed.data;
    let query=db.from('ai_optimization_jobs').update({status:b.action==='pause'?'paused':'queued',lease_token:null,lease_until:null}).eq('id',b.id).eq('user_id',user.id);
    query=b.action==='pause'?query.in('status',['queued','running']):query.eq('status','paused');
    const result=await query.select('id,status');
    if(result.error||!result.data?.length)throw new Error('INPUT:Campaign is not in a controllable state. A failed holdout cannot be resumed.');
    return Response.json(result.data[0]);
  }catch(error){return failure(error);}
}
