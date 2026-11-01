# Accounts and private cloud storage

## Server setup

- Configure `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` in the server environment.
  `python main.py` loads the local Git-ignored `.env`; hosted deployments require
  these variables in the host's secret settings as well. Local changes do not
  configure or redeploy a hosted website.
- Apply `supabase/schema_member_data.sql`, `supabase_schema.sql` and
  `supabase/schema_workspace_autosave.sql` to the same project.
- Keep a stable `LOKI_GATE_SECRET` on every production instance. Changing this
  signing secret invalidates existing logins. Without an explicit signing secret,
  sessions derive their signature from the configured Supabase credential, so
  rotating that credential also signs people out.
- Use HTTPS. Vercel sessions have Secure cookies; all session cookies are HttpOnly,
  SameSite=Lax and expire after 14 days. They survive normal browser/server
  restarts, but not expiry, cleared cookies or secret rotation. Logout clears the
  current browser cookie; it is not remote revocation of a copied cookie.

## What saves

Signed-in workspace pages save changes to allowlisted journals, practice progress,
watchlists and preferences after a two-second debounce. Updates are merged
atomically per key, not whole stale snapshots. Saves retry with bounded backoff
on transient failures. Account mismatch/expired sessions stop saves until reload
or sign-in. Last write wins for the same key; this is not collaborative editing.

The header displays pending/saved/error status. Pending changes remain in local
storage when the database is unavailable; do not clear browser data. Browser
shutdown/crashes can interrupt a pending request, so a successful cloud status is
the confirmation, not simply closing the page.

On another device use **My account → Restore cloud save**. Restoration is explicit
to avoid silently replacing existing local work. Existing manual whole-workspace
save/restore buttons retain their confirmation prompts.

Passwords are managed by Supabase Auth, not workspace JSON. Broker keys, access
tokens and the local Obsidian vault are excluded from cloud workspace storage.
Do not put secrets inside journal text. This does not encrypt journal content
against the server operator/service role.

## Privacy boundaries

- Every cloud operation derives the owner from the verified server cookie.
- Cross-origin writes, forged owners and stale account tabs are blocked.
- Tables have RLS enabled and direct anon/authenticated browser access revoked.
  The server uses its private service credential with explicit owner filtering.
- Account API responses are private and not cacheable. Auth/database requests
  use a validated HTTPS Supabase origin and do not follow redirects.
- In-memory gate throttling is not distributed abuse protection. Before broad
  public release add host-level signup/login throttling and review email
  verification, password recovery and server-side session revocation.
