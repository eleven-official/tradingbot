import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
import { afterEach,it,expect,vi } from 'vitest';

const html=readFileSync(new URL('../../templates/index.html',import.meta.url),'utf8');
const script=readFileSync(new URL('../../static/js/funded_accounts.js',import.meta.url),'utf8');
const pages:JSDOM[]=[];
afterEach(()=>pages.splice(0).forEach(p=>p.window.close()));
function setup(owner='owner'){
  const dom=new JSDOM(html,{url:'https://loki.example/#ai-trading',runScripts:'outside-only'});pages.push(dom);
  const w=dom.window as unknown as Window&typeof globalThis&{LokiStorageOwner:string};w.LokiStorageOwner=owner;
  const state={connected:true,environment:'demo',accounts:[{id:7,name:'<img src=x onerror=alert(1)>'},{id:8,name:'Second account'}],balances:[{account_id:7,currency_id:1,cash:1234}],positions:[],messages:[],expires_at:2000000000};
  const calls=vi.fn(async()=>({ok:true,json:async()=>state}));w.fetch=calls as unknown as typeof fetch;w.eval(script);
  const click=(selector:string)=>(w.document.querySelector(selector) as HTMLElement).click();
  return {w,calls,state,click};
}
it('shows one account workflow at a time without triggering a trade',async()=>{
  const {w,calls,click}=setup();expect(w.document.getElementById('ai-lucid-controls')!.hidden).toBe(true);expect(calls).not.toHaveBeenCalled();
  click('[data-trading-lane="funded"]');await vi.waitFor(()=>expect(calls).toHaveBeenCalledTimes(1));
  expect(w.document.getElementById('ai-lucid-controls')!.hidden).toBe(false);expect(w.document.getElementById('ai-live-controls')!.hidden).toBe(true);
  expect(w.document.getElementById('ai-paper-controls')!.closest('section')!.hidden).toBe(true);
  expect(w.document.querySelector('[data-trading-lane="funded"]')!.getAttribute('aria-pressed')).toBe('true');
});
it('keeps guest credentials off the network',async()=>{
  const {w,calls,click}=setup('guest');click('[data-trading-lane="funded"]');await vi.waitFor(()=>expect(w.document.getElementById('funded-message')!.textContent).toContain('Sign in'));expect(calls).not.toHaveBeenCalled();
});
it('renders broker names as text and filters the selected account',async()=>{
  const {w,click}=setup();click('[data-trading-lane="funded"]');await vi.waitFor(()=>expect(w.document.getElementById('funded-account-details')!.textContent).toContain('1,234'));
  expect(w.document.querySelector('#funded-account-details img')).toBeNull();
  const picker=w.document.getElementById('funded-account-select') as HTMLSelectElement;picker.value='8';picker.dispatchEvent(new w.Event('change'));
  expect(w.document.getElementById('funded-account-details')!.textContent).not.toContain('1,234');
});
it('clears entered tokens immediately and submits only to the owner-bound API',async()=>{
  const {w,calls}=setup();const form=w.document.getElementById('funded-connect-form') as HTMLFormElement;
  (form.elements.namedItem('access_token') as HTMLInputElement).value='private-example-token';form.dispatchEvent(new w.Event('submit',{cancelable:true}));
  expect((form.elements.namedItem('access_token') as HTMLInputElement).value).toBe('');
  await vi.waitFor(()=>expect(calls).toHaveBeenCalledTimes(1));
  const args=calls.mock.calls[0] as unknown as [string,RequestInit];expect(args[0]).toBe('/api/account/funded/connect');expect((args[1].headers as Record<string,string>)['X-Workspace-Owner']).toBe('owner');
  expect(w.localStorage.length).toBe(0);
});
