import { createServerClient } from '@supabase/ssr';
import { NextResponse, type NextRequest } from 'next/server';
export async function proxy(request:NextRequest) {
  // API handlers verify bridge signatures and one-use nonces independently.
  if(request.nextUrl.pathname.startsWith('/api/')&&request.headers.has('x-loki-signature'))return NextResponse.next({request});
  let response=NextResponse.next({request});
  const db=createServerClient(process.env.NEXT_PUBLIC_SUPABASE_URL!,process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,{
    cookies:{getAll:()=>request.cookies.getAll(),setAll(values,headers){
      values.forEach(({name,value})=>request.cookies.set(name,value));response=NextResponse.next({request});
      values.forEach(({name,value,options})=>response.cookies.set(name,value,options));
      Object.entries(headers||{}).forEach(([key,value])=>response.headers.set(key,value));
    }}
  });
  await db.auth.getClaims();
  response.headers.set('Cache-Control','private, no-store');return response;
}
export const config={matcher:['/((?!_next/static|_next/image|favicon.ico|api/optimizer).*)']};
