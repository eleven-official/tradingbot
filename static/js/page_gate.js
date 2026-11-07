/* Extracted from templates/gate.html so the Content-Security-Policy can forbid inline scripts. */
'use strict';
const formEl = document.getElementById('gate-form');
const msgEl = document.getElementById('msg');
const cardEl = document.getElementById('card');
const codeEl = document.getElementById('code');
const setMsg = (text, ok) => { msgEl.className = ok ? 'ok' : ''; msgEl.textContent = text; };

document.getElementById('show-toggle').addEventListener('click', (event) => {
  const hidden = codeEl.type === 'password';
  codeEl.type = hidden ? 'text' : 'password';
  event.target.textContent = hidden ? 'HIDE' : 'SHOW';
  event.target.setAttribute('aria-label', hidden ? 'Hide the code' : 'Show the code');
  codeEl.focus();
});

formEl.addEventListener('submit', async (event) => {
  event.preventDefault();
  const btn = document.getElementById('go');
  const termsEl = document.getElementById('terms-ok');
  const termsBox = document.getElementById('terms-box');
  if (!termsEl.checked) {
    setMsg('Tick the terms box first — the door does not open without the agreement.');
    termsBox.classList.add('unchecked');
    termsEl.focus();
    btn.disabled = false;
    return;
  }
  termsBox.classList.remove('unchecked');
  if (!codeEl.value.trim()) {
    setMsg('Type the access code first — the field is above the tick.');
    codeEl.focus();
    btn.disabled = false;
    return;
  }
  btn.disabled = true;
  setMsg('Checking…');
  try {
    const res = await fetch('/api/gate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: codeEl.value, accepted_terms: termsEl.checked })
    });
    if (res.status === 403) {
      let detail = '';
      try { detail = ((await res.json()) || {}).detail || ''; } catch (err) { detail = ''; }
      if (detail.indexOf('terms') >= 0) {
        setMsg(detail);
        termsBox.classList.add('unchecked');
      } else {
        setMsg('That is not the code — the words themselves need to match (spacing, caps and punctuation are forgiven). "Need help getting in?" below has the usual fixes.');
        cardEl.classList.remove('shake');
        void cardEl.offsetWidth; // restart the animation
        cardEl.classList.add('shake');
      }
      btn.disabled = false;
      return;
    }
    if (res.status === 429) {
      setMsg('Ten wrong tries earned a five-minute break — the clock clears itself, nothing to reset. "Need help getting in?" has more.');
      btn.disabled = false;
      return;
    }
    if (!res.ok) {
      setMsg('Loki is updating right now — give it a minute and try again.');
      btn.disabled = false;
      return;
    }
    setMsg('Welcome in — opening the workspace…', true);
    window.location.href = '/';
  } catch (err) {
    setMsg('Connection hiccup — check the internet and try again.');
    btn.disabled = false;
  }
});

const helpBtn = document.getElementById('need-help');
const helpBlock = document.getElementById('help-block');
if (helpBtn && helpBlock) {
  helpBtn.addEventListener('click', () => {
    const closing = !helpBlock.hidden;
    helpBlock.hidden = closing;
    helpBtn.setAttribute('aria-expanded', String(!closing));
    if (!closing) helpBlock.scrollIntoView({ block: 'nearest' });
  });
}
const forgetBtn = document.getElementById('forget-device');
if (forgetBtn) {
  forgetBtn.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/gate/forget', { method: 'POST' });
      if (!res.ok) throw new Error('eraser unavailable');
    } catch (err) {
      setMsg('Could not erase access — check your connection and try again.');
      return;
    }
    document.cookie = 'loki_gate=; Max-Age=0; path=/';
    document.cookie = 'loki_terms=; Max-Age=0; path=/';
    setMsg('Erased. If this browser was unlocked, the very next page load shows this gate again.', true);
  });
}
