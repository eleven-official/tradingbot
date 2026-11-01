import 'server-only';
import { cookies } from 'next/headers';
import { createServerClient } from '@supabase/ssr';
import { verifyBridge } from './bridge';
import { admin } from './admin';
export async function server() {
  const jar=await cookies();
  return createServerClient(process.env.NEXT_PUBLIC_SUPABASE_URL!,process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,{
    cookies:{getAll:()=>jar.getAll(),setAll(values){try{values.forEach(({name,value,options})=>jar.set(name,value,options));}catch{/* Proxy refreshes cookies for Server Components. */}}}
  });
}
export async function authenticated(request?:Request) {
  if(request?.headers.has('x-loki-signature')) {
    const identity=verifyBridge(request,await request.clone().text(),process.env.LOKI_RESEARCH_BRIDGE_SECRET,process.env.NEXT_PUBLIC_SUPABASE_URL);
    const service=admin();
    const replay=await service.rpc('consume_research_bridge_nonce',{p_nonce:request.headers.get('x-loki-nonce')});
    if(replay.error||replay.data!==true)throw new Error('UNAUTHENTICATED');
    const {data,error}=await service.auth.admin.getUserById(identity.uid);
    if(error||!data.user||data.user.banned_until&&Date.parse(data.user.banned_until)>Date.now())throw new Error('UNAUTHENTICATED');
    // Read routes retain RLS through the ordinary browser client. Bridge reads
    // use explicit owner filters because this service client bypasses RLS.
    return {db:service,user:data.user};
  }
  const db=await server(); const {data,error}=await db.auth.getUser();
  if(error||!data.user)throw new Error('UNAUTHENTICATED');
  return {db,user:data.user};
}
