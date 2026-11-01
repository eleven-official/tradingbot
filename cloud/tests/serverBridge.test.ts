import { createHash,createHmac } from 'node:crypto';
import { beforeEach,afterEach,it,expect,vi } from 'vitest';
const mocks=vi.hoisted(()=>({rpc:vi.fn(),getUserById:vi.fn(),from:vi.fn()}));
vi.mock('server-only',()=>({}));
vi.mock('../lib/admin',()=>({admin:()=>({rpc:mocks.rpc,from:mocks.from,auth:{admin:{getUserById:mocks.getUserById}}})}));
import { authenticated } from '../lib/server';
import { GET } from '../app/api/state/route';
const uid='11111111-1111-4111-8111-111111111111',project='https://test.supabase.co',secret='bridge-secret-for-testing-only-'.repeat(2);
function request(){
  const timestamp=String(Date.now()),nonce='22222222-2222-4222-8222-222222222222',identity=Buffer.from(JSON.stringify({uid,project})).toString('base64url');
  const message=[timestamp,nonce,'GET','/api/state',createHash('sha256').update('').digest('hex'),identity].join('\n');
  return new Request('https://cloud.example/api/state',{headers:{'x-loki-time':timestamp,'x-loki-nonce':nonce,'x-loki-identity':identity,'x-loki-signature':createHmac('sha256',secret).update(message).digest('hex')}});
}
beforeEach(()=>{vi.clearAllMocks();vi.stubEnv('LOKI_RESEARCH_BRIDGE_SECRET',secret);vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL',project);mocks.rpc.mockResolvedValue({data:true,error:null});mocks.getUserById.mockResolvedValue({data:{user:{id:uid}},error:null});});
afterEach(()=>vi.unstubAllEnvs());
it('checks one-use nonce and current Auth identity before returning owner-scoped context',async()=>{const result=await authenticated(request());expect(result.user.id).toBe(uid);expect(mocks.rpc).toHaveBeenCalledWith('consume_research_bridge_nonce',{p_nonce:'22222222-2222-4222-8222-222222222222'});expect(mocks.getUserById).toHaveBeenCalledWith(uid);});
it('rejects replayed assertions before accepting the identity',async()=>{mocks.rpc.mockResolvedValue({data:false,error:null});await expect(authenticated(request())).rejects.toThrow('UNAUTHENTICATED');expect(mocks.getUserById).not.toHaveBeenCalled();});
it('fails closed when the nonce store is missing or unavailable',async()=>{mocks.rpc.mockResolvedValue({data:null,error:{message:'missing table'}});await expect(authenticated(request())).rejects.toThrow('UNAUTHENTICATED');});
it('rejects deleted and banned users',async()=>{mocks.getUserById.mockResolvedValue({data:{user:null},error:null});await expect(authenticated(request())).rejects.toThrow('UNAUTHENTICATED');mocks.getUserById.mockResolvedValue({data:{user:{id:uid,banned_until:new Date(Date.now()+60000).toISOString()}},error:null});await expect(authenticated(request())).rejects.toThrow('UNAUTHENTICATED');});
it('keeps explicit tenant predicates on every service-role state query',async()=>{
  const predicates:{table:string;column:string;owner:string}[]=[];
  mocks.from.mockImplementation((table:string)=>{
    const query={select:vi.fn(),eq:vi.fn(),order:vi.fn(),limit:vi.fn(),maybeSingle:vi.fn(),then:undefined} as Record<string,unknown>;
    for(const key of ['select','order','limit','maybeSingle'])query[key]=vi.fn().mockReturnValue(query);
    query.eq=vi.fn((column:string,owner:string)=>{predicates.push({table,column,owner});return query;});
    query.then=(resolve:(v:unknown)=>void)=>Promise.resolve({data:table==='profiles'?{role:'researcher'}:[],error:null}).then(resolve);
    return query;
  });
  const response=await GET(request());expect(response.status).toBe(200);expect(predicates).toHaveLength(6);expect(predicates.every(p=>p.owner===uid&&p.column===(p.table==='profiles'?'id':'user_id'))).toBe(true);expect(response.headers.get('cache-control')).toContain('no-store');
});
