import { createHash,createHmac } from 'node:crypto';
import { it,expect } from 'vitest';
import { verifyBridge } from '../lib/bridge';
const secret='test-bridge-secret-'.repeat(3),project='https://test.supabase.co',uid='11111111-1111-4111-8111-111111111111',now=1700000000000;
function signed(body='',method='GET',path='/api/state',identity={uid,project}) {
  const encoded=Buffer.from(JSON.stringify(identity)).toString('base64url'),nonce='22222222-2222-4222-8222-222222222222',timestamp=String(now);
  const payload=[timestamp,nonce,method,path,createHash('sha256').update(body).digest('hex'),encoded].join('\n');
  return new Request('https://cloud.example'+path,{method,headers:{'x-loki-time':timestamp,'x-loki-nonce':nonce,'x-loki-identity':encoded,'x-loki-signature':createHmac('sha256',secret).update(payload).digest('hex')},...(body?{body}:{})});
}
it('verifies an owner-bound server assertion',()=>{expect(verifyBridge(signed(),'',secret,project,now)).toEqual({uid,project});});
it('binds signatures to the body, method and path',()=>{const req=signed('{}','POST','/api/jobs');expect(()=>verifyBridge(req,'{"dataset_id":"other"}',secret,project,now)).toThrow();expect(()=>verifyBridge(new Request('https://cloud.example/api/datasets',{method:'POST',headers:req.headers}),'{}',secret,project,now)).toThrow();expect(()=>verifyBridge(new Request(req.url,{method:'PATCH',headers:req.headers}),'{}',secret,project,now)).toThrow();});
it('rejects expired assertions and incorrect secrets',()=>{expect(()=>verifyBridge(signed(),'',secret,project,now+31000)).toThrow();expect(()=>verifyBridge(signed(),'','incorrect-secret'.repeat(3),project,now)).toThrow();});
it('rejects a different Supabase identity namespace',()=>{expect(()=>verifyBridge(signed(),'',secret,'https://another.supabase.co',now)).toThrow();});
it('rejects missing configuration, malformed owners and unsigned requests',()=>{expect(()=>verifyBridge(signed(),'',undefined,project,now)).toThrow();expect(()=>verifyBridge(signed('','GET','/api/state',{uid:'not-a-uuid',project}),'',secret,project,now)).toThrow();expect(()=>verifyBridge(new Request('https://cloud.example/api/state'),'',secret,project,now)).toThrow();});
