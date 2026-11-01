import { admin } from '../../../lib/admin';
import { cronAuthorized } from '../../../lib/http';
import { optimizerTick } from '../../../services/optimizer';
import { ingestionTick } from '../../../services/ingestion';
import type { Dataset,Job } from '../../../lib/types';

export const runtime='nodejs';
export const maxDuration=60;
export const dynamic='force-dynamic';
export async function GET(request:Request) {
  if(!cronAuthorized(request))return Response.json({error:'Unauthorized scheduler'},{status:401});
  try{
    const db=admin();
    const {data,error}=await db.rpc('claim_cloud_work');
    if(error)throw error;
    if(!data)return Response.json({status:'idle',note:'No queued work. Waiting is not proof of a 75% edge.'});
    const result=data.kind==='dataset'?await ingestionTick(db,data.item as Dataset,data.token):await optimizerTick(db,data.item as Job,data.token);
    return Response.json(result,{headers:{'Cache-Control':'no-store'}});
  }catch{
    // An unknown result never retries in the same invocation. Lease expiry permits
    // the next cloud tick to resume from the last committed cursor.
    return Response.json({error:'Cloud worker failed; lease expiry enables bounded resume.'},{status:503,headers:{'Cache-Control':'no-store'}});
  }
}
