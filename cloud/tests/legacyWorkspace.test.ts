import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
import { afterEach,it,expect,vi } from 'vitest';
const script=readFileSync(new URL('../../static/js/cloud_research.js',import.meta.url),'utf8');
const pages:JSDOM[]=[];
afterEach(()=>{pages.splice(0).forEach(page=>page.window.close());});
function workspace({owner='11111111-1111-4111-8111-111111111111',configured=true,role='operator',symbol='SPY'}={}) {
  const dom=new JSDOM('<section id="cloud-research"><button id="cloud-research-refresh">Refresh</button><p id="cloud-research-message"></p><div id="cloud-research-content"></div></section>',{url:'https://loki.example/#cloud-research',runScripts:'outside-only',pretendToBeVisual:true});pages.push(dom);
  const w=dom.window as unknown as Window&typeof globalThis&{LokiStorageOwner:string;currentSymbol:string;inlineMetrics:()=>HTMLElement};
  w.LokiStorageOwner=owner;w.currentSymbol=symbol;w.inlineMetrics=()=>w.document.createElement('div');
  const state={profile:{role},datasets:[],jobs:[],runs:[],trades:[],equity:[]};
  const calls=vi.fn(async(url:string,options?:RequestInit)=>({ok:true,json:async()=>url.endsWith('/status')?{configured}:url.endsWith('/state')?state:{id:'created'}}));
  w.fetch=calls as unknown as typeof fetch;w.eval(script);
  return {dom,w,calls,state};
}
it('loads cloud research through the existing account bridge, never the cloud host directly',async()=>{
  const {w,calls}=workspace();await vi.waitFor(()=>expect(w.document.querySelector('form')).not.toBeNull());expect(calls.mock.calls.map(c=>c[0])).toEqual(['/api/account/research/status','/api/account/research/state']);expect(w.document.body.textContent).toContain('No cloud trades');
});
it('displays setup instructions without querying research state when the bridge is missing',async()=>{
  const {w,calls}=workspace({configured:false});await vi.waitFor(()=>expect(w.document.body.textContent).toContain('not configured'));expect(calls).toHaveBeenCalledTimes(1);expect(w.document.querySelector('form')).toBeNull();
});
it('does not fetch cloud data for a guest',async()=>{
  const {w,calls}=workspace({owner:'guest'});await vi.waitFor(()=>expect(w.document.body.textContent).toContain('Sign in'));expect(calls).not.toHaveBeenCalled();
});
it('prevents researchers from queuing paid cloud work',async()=>{
  const {w}=workspace({role:'researcher'});await vi.waitFor(()=>expect(w.document.querySelector('form')).not.toBeNull());expect((w.document.querySelector('form button') as HTMLButtonElement).disabled).toBe(true);
});
it('shares the active stock symbol and submits owner-bound research creation',async()=>{
  const {w,calls}=workspace({symbol:'AAPL'});await vi.waitFor(()=>expect(w.document.querySelector('form')).not.toBeNull());const form=w.document.querySelector('form')!;expect((form.querySelector('input') as HTMLInputElement).value).toBe('AAPL');form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await vi.waitFor(()=>expect(calls.mock.calls.some(c=>c[0].endsWith('/datasets'))).toBe(true));const call=calls.mock.calls.find(c=>c[0].endsWith('/datasets'))!;expect(JSON.parse(String(call[1]?.body))).toEqual({symbol:'AAPL',asset_kind:'stock',source:'alpaca',years:20,timeframe:'1d'});expect((call[1]?.headers as Record<string,string>)['X-Workspace-Owner']).toBe(w.LokiStorageOwner);
});
