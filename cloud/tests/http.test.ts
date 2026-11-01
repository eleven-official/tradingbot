import { afterEach,it,expect,vi } from 'vitest';
import { cronAuthorized,sameOrigin } from '../lib/http';
afterEach(()=>vi.unstubAllEnvs());
it('requires a full strong cron bearer secret',()=>{vi.stubEnv('CRON_SECRET','x'.repeat(40));expect(cronAuthorized(new Request('https://a/api'))).toBe(false);expect(cronAuthorized(new Request('https://a/api',{headers:{authorization:'Bearer '+'x'.repeat(40)}}))).toBe(true);});
it('rejects cross-origin browser mutations',()=>{expect(()=>sameOrigin(new Request('https://a/api',{headers:{origin:'https://evil.example'}}))).toThrow('FORBIDDEN');expect(()=>sameOrigin(new Request('https://a/api',{headers:{origin:'https://a'}}))).not.toThrow();});
