import { NextResponse } from 'next/server';
import { server } from '../../../lib/server';
export async function GET(request:Request) {
  const url=new URL(request.url),code=url.searchParams.get('code');
  if(code){const db=await server();const {error}=await db.auth.exchangeCodeForSession(code);if(!error)return NextResponse.redirect(new URL('/',url.origin));}
  return NextResponse.redirect(new URL('/login?error=confirmation_failed',url.origin));
}
