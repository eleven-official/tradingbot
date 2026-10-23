-- Revenue ledger — run this ONCE in the Loki Supabase project
-- (Dashboard → SQL editor → paste → Run). The service key the server already
-- holds records rows through PostgREST; no other grant is needed.
--
-- One row per recorded profit event: the month (period), who the profit
-- belongs to (subject), the recorded gross figure, and the house cut the
-- SERVER computed for it (30% = 3000 basis points of gross, rounded half-up
-- to the cent — the SQL CHECK keeps |cut| <= |gross| so a row can never
-- disagree with its own gross). Rows are append-only by design: corrections
-- arrive as new negative events, never as edits. Figures are operator-
-- private: the website reads them only through the server's service key.
--
-- Negative gross is legal: it models a loss month or a correction, and the
-- cut mirrors the sign (a clawback pulls the books down honestly).

create table if not exists public.revenue_ledger (
    id         uuid primary key default gen_random_uuid(),
    period     text not null check (period ~ '^\d{4}-(0[1-9]|1[0-2])$'),
    subject    text not null check (char_length(subject) between 1 and 80),
    gross      numeric not null check (abs(gross) < 1e12),
    cut        numeric not null check (abs(cut) <= abs(gross) and abs(cut) < 1e12),
    currency   text not null default 'USD' check (currency ~ '^[A-Z]{3}$'),
    source     text not null default 'manual' check (char_length(source) between 1 and 40),
    note       text not null default '' check (char_length(note) <= 240),
    created_at timestamptz not null default now()
);

-- Fast period-sorted reads for statements.
create index if not exists revenue_ledger_period_idx
    on public.revenue_ledger (period, currency);

-- PostgREST reads for the operator-facing statement go through the service
-- key, which bypasses RLS. This policy only matters if a website anon key
-- ever queries the table — publishing select keeps that read-only.
alter table public.revenue_ledger enable row level security;
drop policy if exists "ledger is readable, never writable, from the web" on public.revenue_ledger;
create policy "ledger is readable, never writable, from the web"
    on public.revenue_ledger for select using (true);
