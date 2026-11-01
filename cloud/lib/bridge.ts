import { createHash,createHmac,timingSafeEqual } from 'node:crypto';
export type BridgeIdentity={uid:string;project:string};
export function verifyBridge(request:Request,body:string,secret:string|undefined,project:string|undefined,now=Date.now()):BridgeIdentity {
  if(!secret||secret.length<32||!project)throw new Error('UNAUTHENTICATED');
  const timestamp=request.headers.get('x-loki-time')||'',nonce=request.headers.get('x-loki-nonce')||'',identity=request.headers.get('x-loki-identity')||'',signature=request.headers.get('x-loki-signature')||'';
  const uuid=/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
  if(!/^\d{13}$/.test(timestamp)||Math.abs(now-Number(timestamp))>30000||!uuid.test(nonce)||identity.length>2048||!/^[a-f0-9]{64}$/.test(signature))throw new Error('UNAUTHENTICATED');
  const payload=[timestamp,nonce,request.method,new URL(request.url).pathname,createHash('sha256').update(body).digest('hex'),identity].join('\n');
  const expected=createHmac('sha256',secret).update(payload).digest();
  if(!timingSafeEqual(expected,Buffer.from(signature,'hex')))throw new Error('UNAUTHENTICATED');
  let parsed:BridgeIdentity;
  try{parsed=JSON.parse(Buffer.from(identity,'base64url').toString('utf8')) as BridgeIdentity;}catch{throw new Error('UNAUTHENTICATED');}
  if(!parsed||typeof parsed.uid!=='string'||!uuid.test(parsed.uid)||parsed.project!==project.replace(/\/$/,''))throw new Error('UNAUTHENTICATED');
  return parsed;
}
