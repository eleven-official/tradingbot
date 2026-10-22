-- Shared dive leaderboard — run this ONCE in the Loki Supabase project
-- (Dashboard → SQL editor → paste → Run). The service key the server already
-- holds writes rows through PostgREST; no other grant is needed.
--
-- One row per board name. A publish keeps the higher of the existing and the
-- incoming best (the server compares before writing), and counts finished dives.
-- Rows are public-readable by design: a leaderboard is public data.

create table if not exists public.dive_scores (
    nickname   text primary key,
    best_score integer not null default 0 check (best_score >= 0 and best_score <= 1000000),
    dives      integer not null default 0 check (dives >= 0),
    updated_at timestamptz not null default now()
);

-- PostgREST reads for the board listing through the service key.
-- (The service role bypasses RLS; this policy only matters if a website
--  anon key ever queries the table.)
alter table public.dive_scores enable row level security;
drop policy if exists "board is publicly readable" on public.dive_scores;
create policy "board is publicly readable"
    on public.dive_scores for select using (true);
