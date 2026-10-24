# Account leaderboard and private workspace (2.24.0)

Uses the existing server-only Supabase credentials. No browser database key is needed.

1. Open the existing project's **SQL Editor**.
2. Run `supabase/schema_member_data.sql` in full. It is safe to run again.
3. Reload the game and sign in. Publish a finished score explicitly.
4. Open **My account**, save a workspace, then sign in on another device and restore it.

The migration creates `member_dive_scores`, `member_workspace`, and an atomic
`publish_member_dive` function. Foreign keys bind both tables to Supabase users.
RLS is enabled with direct browser-role access revoked. Only the service role
can access them; the API derives the owner from a verified signed session.
Public rankings explicitly select nicknames, best scores, counts and timestamps.

Legacy nickname-only scores remain untouched in `dive_scores`. They are not
assigned to accounts: there is no evidence of which person owned a nickname.
Scores remain self-reported, not cheat-verified or suitable for prize payouts.
The local-development file board is still nickname-based; Vercel uses Supabase.

Workspace saves are explicit snapshots, not automatic live syncing. The server
allowlists journal/game keys, caps saves at 500 KB, and excludes known credential
keys. Never put credentials in journal text. Account browser copies are scoped
by user, but are not encrypted against someone who controls that browser profile.
Old guest data can be manually exported and imported by its owner.

Session cookies are HttpOnly and Secure on Vercel. Keep the Supabase service key
and `LOKI_GATE_SECRET` server-side. Rotating the signing secret invalidates old
sessions. Auth/account responses use `Cache-Control: private, no-store`.

If the tables are missing or Supabase is unreachable, API calls return 503 and
the UI shows the reason; it does not claim to save data locally as a substitute.
