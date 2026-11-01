'use client';
import { useState } from 'react';
import { browser } from '../../lib/browser';
export default function Login() {
  const [email,setEmail]=useState(''),[password,setPassword]=useState(''),[signup,setSignup]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  async function submit(event:React.FormEvent) {
    event.preventDefault();setBusy(true);setMessage('');
    try {
      const db=browser();
      const result=signup?await db.auth.signUp({email,password,options:{emailRedirectTo:location.origin+'/auth/callback'}}):await db.auth.signInWithPassword({email,password});
      if(result.error)throw result.error;
      if(result.data.session)location.assign('/');else setMessage('Check your email to confirm your account.');
    }catch{setMessage('Authentication failed. Check your details or confirmation email.');}finally{setBusy(false);}
  }
  return <main className="login"><span className="eyebrow">LOKI / CLOUD RESEARCH</span><h1>Evidence before execution.</h1><p>Sign in to your isolated research workspace.</p><form onSubmit={submit} className="panel stack"><h2>{signup?'Create account':'Sign in'}</h2><label>Email<input type="email" autoComplete="email" required value={email} onChange={e=>setEmail(e.target.value)}/></label><label>Password<input type="password" autoComplete={signup?'new-password':'current-password'} minLength={12} required value={password} onChange={e=>setPassword(e.target.value)}/></label><button disabled={busy}>{busy?'Working…':signup?'Create account':'Sign in'}</button><button type="button" className="secondary" onClick={()=>{setSignup(!signup);setMessage('');}}>{signup?'Use an existing account':'Create a research account'}</button><p role="status">{message}</p><small>New accounts have read-only researcher access. An administrator grants cloud compute access.</small></form></main>;
}
