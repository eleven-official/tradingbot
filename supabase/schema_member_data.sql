-- Run once in the existing Loki Supabase project's SQL editor.
-- Separate tables preserve legacy nickname-only scores without assigning them
-- to accounts whose ownership cannot be established.
begin;
create table if not exists public.member_dive_scores (
  user_id uuid primary key references auth.users(id) on delete cascade,
  nickname text not null check (char_length(nickname) between 2 and 24),
  best_score integer not null check (best_score between 0 and 1000000),
  dives integer not null default 1 check (dives >= 1),
  updated_at timestamptz not null default now()
);
create table if not exists public.member_workspace (
  user_id uuid primary key references auth.users(id) on delete cascade,
  items jsonb not null default '{}'::jsonb check (jsonb_typeof(items) = 'object' and octet_length(items::text) <= 600000),
  updated_at timestamptz not null default now()
);
alter table public.member_dive_scores enable row level security;
alter table public.member_workspace enable row level security;
-- Browser roles have no direct access. The authenticated application server
-- derives ownership from its verified session, never from request parameters.
revoke all on public.member_dive_scores, public.member_workspace from public, anon, authenticated;
grant select, insert, update, delete on public.member_dive_scores, public.member_workspace to service_role;
create index if not exists member_dive_ranking on public.member_dive_scores (best_score desc, updated_at asc);

create or replace function public.publish_member_dive(p_user_id uuid, p_nickname text, p_best integer)
returns setof public.member_dive_scores
language sql security invoker set search_path = public
as $$
  insert into public.member_dive_scores as score (user_id, nickname, best_score)
  values (p_user_id, p_nickname, p_best)
  on conflict (user_id) do update set
    nickname = excluded.nickname,
    best_score = greatest(score.best_score, excluded.best_score),
    dives = score.dives + 1,
    updated_at = now()
  returning *;
$$;
revoke all on function public.publish_member_dive(uuid, text, integer) from public, anon, authenticated;
grant execute on function public.publish_member_dive(uuid, text, integer) to service_role;
commit;
