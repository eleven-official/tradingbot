import 'server-only';
import { createClient } from '@supabase/supabase-js';
export function admin() {
  const url=process.env.NEXT_PUBLIC_SUPABASE_URL,key=process.env.SUPABASE_SERVICE_KEY;
  if(!url||!key)throw new Error('Server database configuration missing');
  return createClient(url,key,{auth:{persistSession:false,autoRefreshToken:false},global:{fetch:(input,init)=>fetch(input,{...init,signal:AbortSignal.timeout(12000),redirect:'error'})}});
}
