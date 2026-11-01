-- Additive upgrade ONLY for installations of the original cloud schema.
-- Fresh installations already include this in schema.sql.
begin;
create table if not exists public.research_bridge_nonces (
  nonce uuid primary key, expires_at timestamptz not null default now()+interval '1 minute'
);
create index if not exists research_bridge_nonce_expiry on public.research_bridge_nonces(expires_at);
alter table public.research_bridge_nonces enable row level security;
revoke all on public.research_bridge_nonces from public,anon,authenticated;
grant all on public.research_bridge_nonces to service_role;
create or replace function public.consume_research_bridge_nonce(p_nonce uuid)
returns boolean language plpgsql security invoker set search_path=public as $$
begin
  delete from public.research_bridge_nonces where nonce in
    (select nonce from public.research_bridge_nonces where expires_at<now() order by expires_at limit 1000);
  insert into public.research_bridge_nonces(nonce) values(p_nonce) on conflict do nothing;
  return found;
end $$;
revoke all on function public.consume_research_bridge_nonce(uuid) from public,anon,authenticated;
grant execute on function public.consume_research_bridge_nonce(uuid) to service_role;
commit;
