import { timingSafeEqual } from 'node:crypto';
export function cronAuthorized(request:Request):boolean {
  const secret=process.env.CRON_SECRET;
  if(!secret||secret.length<32)return false;
  const expected=Buffer.from('Bearer '+secret),actual=Buffer.from(request.headers.get('authorization')||'');
  return actual.length===expected.length&&timingSafeEqual(actual,expected);
}
export function sameOrigin(request:Request):void {
  const origin=request.headers.get('origin');
  if(request.headers.get('sec-fetch-site')==='cross-site'||(origin&&new URL(origin).origin!==new URL(request.url).origin))throw new Error('FORBIDDEN');
}
export function failure(error:unknown) {
  const message=error instanceof Error?error.message:'';
  const status=message==='UNAUTHENTICATED'?401:message==='FORBIDDEN'?403:message.startsWith('INPUT:')?422:503;
  return Response.json({error:status===503?'Cloud service unavailable; retry shortly.':message.replace('INPUT:','')},{status,headers:{'Cache-Control':'private, no-store'}});
}
