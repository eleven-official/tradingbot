import { authenticated } from './server';
import { admin } from './admin';
export async function operator(request?:Request) {
  const {user}=await authenticated(request),db=admin();
  const created=await db.from('profiles').upsert({id:user.id,display_name:String(user.user_metadata?.display_name||'').slice(0,80)},{onConflict:'id',ignoreDuplicates:true});
  if(created.error)throw new Error('Profile unavailable');
  const {data,error}=await db.from('profiles').select('role').eq('id',user.id).single();
  if(error||!data||!['operator','admin'].includes(data.role))throw new Error('FORBIDDEN');
  return {db,user};
}
