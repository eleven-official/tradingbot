-- Loki Cloud: run in Supabase SQL Editor, in a NEW project or after review.
-- No existing Loki tables are dropped. All worker writes are service-role only.
begin;
create extension if not exists vector with schema extensions;
create extension if not exists pgcrypto with schema extensions;

-- One-use signed requests from the existing Loki server; no browser grants.
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

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null default '' check (length(display_name)<=80),
  role text not null default 'researcher' check (role in ('researcher','operator','admin')),
  created_at timestamptz not null default now()
);

create table if not exists public.market_datasets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  symbol text not null check (symbol ~ '^[A-Z][A-Z0-9.]{0,11}$'),
  asset_kind text not null default 'stock' check (asset_kind in ('stock','option')),
  timeframe text not null default '1d' check (timeframe in ('1d','15m','5m')),
  requested_years integer not null check (requested_years in (10,15,20)),
  source text not null check (source in ('alpaca','upload')),
  source_verified boolean not null default false,
  status text not null default 'ingesting' check (status in ('ingesting','featurizing','ready','waiting_data','failed')),
  first_at timestamptz, last_at timestamptz, train_end timestamptz, validation_end timestamptz,
  raw_count integer not null default 0, feature_count integer not null default 0,
  fee_bps double precision not null default 10 check (fee_bps between 0 and 100),
  slippage_bps double precision not null default 5 check (slippage_bps between 1 and 100),
  option_commission double precision not null default 0.65 check (option_commission between 0.01 and 20),
  embedding_version text not null default 'causal12_v1',
  training_win_rate double precision not null default 0.5 check(training_win_rate between 0 and 1),
  cursor jsonb not null default '{"phase":"fetch"}',
  lease_token uuid, lease_until timestamptz,
  holdout_run_id uuid, last_error text, created_at timestamptz not null default now(),
  unique (id,user_id)
);

create table if not exists public.market_bars (
  dataset_id uuid not null references public.market_datasets(id) on delete cascade,
  observed_at timestamptz not null,
  open double precision not null check (open>0), high double precision not null,
  low double precision not null, close double precision not null check(close>0),
  volume double precision not null check(volume>=0),
  primary key(dataset_id,observed_at),
  check(low>0 and low<=least(open,close) and high>=greatest(open,close))
);

create table if not exists public.historical_features (
  id bigint generated always as identity primary key,
  dataset_id uuid not null,
  user_id uuid not null,
  observed_at timestamptz not null, outcome_at timestamptz not null,
  embedding extensions.vector(12) not null,
  regime text not null check(regime in ('up','down','range','stress')),
  -- Next-bar open-to-close LONG result AFTER fees/spread/slippage.
  net_return double precision not null check(net_return between -1 and 10),
  cost_return double precision not null check(cost_return between 0 and 2),
  contract_key text not null default '',
  option_context jsonb,
  foreign key(dataset_id,user_id) references public.market_datasets(id,user_id) on delete cascade,
  check(outcome_at>observed_at), unique(dataset_id,observed_at,contract_key)
);
create index if not exists historical_features_dataset_time on public.historical_features(dataset_id,observed_at,id);
create index if not exists historical_features_vector on public.historical_features using hnsw(embedding extensions.vector_l2_ops);

create table if not exists public.ai_optimization_jobs (
  id uuid primary key default gen_random_uuid(), user_id uuid not null,
  dataset_id uuid not null, target_win_rate double precision not null default 0.75 check(target_win_rate=0.75),
  status text not null default 'queued' check(status in ('queued','running','qualified','paused','waiting_new_data','blocked')),
  max_trials integer not null default 128 check(max_trials between 1 and 512),
  work jsonb not null default '{"trial":0,"stage":"validation","cursor":null,"stats":{}}',
  lease_token uuid, lease_until timestamptz, next_attempt_at timestamptz not null default now(),
  last_error text, created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  foreign key(dataset_id,user_id) references public.market_datasets(id,user_id) on delete cascade,
  unique(id,user_id)
);
create unique index if not exists one_running_campaign_per_dataset on public.ai_optimization_jobs(dataset_id)
  where status in ('queued','running');

create table if not exists public.ai_optimization_runs (
  id uuid primary key, job_id uuid not null, user_id uuid not null,
  trial integer not null, stage text not null check(stage in ('validation','certification')),
  parameters jsonb not null, metrics jsonb not null,
  qualified boolean not null default false, created_at timestamptz not null default now(),
  foreign key(job_id,user_id) references public.ai_optimization_jobs(id,user_id) on delete cascade,
  unique(job_id,trial,stage)
);

create table if not exists public.trade_logs (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references public.profiles(id) on delete cascade,
  model_run_id uuid references public.ai_optimization_runs(id),
  symbol text not null, asset_kind text not null check(asset_kind in ('stock','option')),
  contract_key text, side text not null check(side in ('buy','sell')),
  mode text not null default 'paper' check(mode='paper'),
  status text not null check(status in ('blocked','intent','submitted','partial','filled','rejected','unknown','closed')),
  client_order_id uuid not null unique, broker_order_id text,
  quantity numeric not null check(quantity>0), limit_price numeric check(limit_price>0),
  filled_quantity numeric not null default 0, average_fill numeric,
  realized_pnl numeric, fees numeric, decision jsonb not null,
  created_at timestamptz not null default now()
);
create index if not exists trade_logs_owner_time on public.trade_logs(user_id,created_at desc);

create table if not exists public.equity_snapshots (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.profiles(id) on delete cascade,
  equity numeric not null, cash numeric not null, positions jsonb not null default '[]',
  source text not null check(source in ('alpaca_paper','research_simulation')),
  observed_at timestamptz not null default now()
);

-- No browser can write datasets, trial metrics, qualification, roles or orders.
do $$ declare t text; begin
  foreach t in array array['profiles','market_datasets','market_bars','historical_features',
    'ai_optimization_jobs','ai_optimization_runs','trade_logs','equity_snapshots'] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('revoke all on public.%I from public,anon,authenticated',t);
    execute format('grant all on public.%I to service_role',t);
  end loop;
end $$;
grant select on public.profiles,public.market_datasets,public.ai_optimization_jobs,
  public.ai_optimization_runs,public.trade_logs,public.equity_snapshots to authenticated;
grant usage,select on all sequences in schema public to service_role;
create policy profiles_own_read on public.profiles for select to authenticated using(id=auth.uid());
create policy datasets_own_read on public.market_datasets for select to authenticated using(user_id=auth.uid());
create policy jobs_own_read on public.ai_optimization_jobs for select to authenticated using(user_id=auth.uid());
create policy runs_own_read on public.ai_optimization_runs for select to authenticated using(user_id=auth.uid());
create policy trades_own_read on public.trade_logs for select to authenticated using(user_id=auth.uid());
create policy equity_own_read on public.equity_snapshots for select to authenticated using(user_id=auth.uid());

-- Worker leases survive Vercel invocations. Expired workers cannot checkpoint.
create or replace function public.claim_cloud_work()
returns jsonb language plpgsql security invoker set search_path=public as $$
declare d public.market_datasets; j public.ai_optimization_jobs; token uuid:=gen_random_uuid();
begin
  select * into d from public.market_datasets where source='alpaca' and status in ('ingesting','featurizing')
    and (lease_until is null or lease_until<now()) order by created_at for update skip locked limit 1;
  if found then
    update public.market_datasets set lease_token=token,lease_until=now()+interval '90 seconds' where id=d.id;
    return jsonb_build_object('kind','dataset','token',token,'item',to_jsonb(d));
  end if;
  select * into j from public.ai_optimization_jobs where status in ('queued','running')
    and next_attempt_at<=now() and (lease_until is null or lease_until<now())
    order by updated_at for update skip locked limit 1;
  if found then
    update public.ai_optimization_jobs set status='running',lease_token=token,lease_until=now()+interval '90 seconds' where id=j.id;
    return jsonb_build_object('kind','job','token',token,'item',to_jsonb(j));
  end if;
  return null;
end $$;

create or replace function public.commit_dataset_work(p_id uuid,p_token uuid,p_patch jsonb,
  p_bars jsonb default '[]',p_features jsonb default '[]')
returns void language plpgsql security invoker set search_path=public,extensions as $$
declare d public.market_datasets; r jsonb;
begin
  select * into d from public.market_datasets where id=p_id for update;
  if not found or p_token is null or d.lease_until is null or d.lease_token is distinct from p_token or d.lease_until<=now() then raise exception 'stale_lease'; end if;
  if jsonb_array_length(p_bars)>10000 or jsonb_array_length(p_features)>500 then raise exception 'batch_limit'; end if;
  for r in select * from jsonb_array_elements(p_bars) loop
    insert into public.market_bars values(p_id,(r->>'observed_at')::timestamptz,
      (r->>'open')::float8,(r->>'high')::float8,(r->>'low')::float8,(r->>'close')::float8,(r->>'volume')::float8)
      on conflict do nothing;
  end loop;
  for r in select * from jsonb_array_elements(p_features) loop
    insert into public.historical_features(dataset_id,user_id,observed_at,outcome_at,embedding,regime,net_return,cost_return,contract_key,option_context)
      values(p_id,d.user_id,(r->>'observed_at')::timestamptz,(r->>'outcome_at')::timestamptz,
        (r->'embedding')::text::extensions.vector,r->>'regime',(r->>'net_return')::float8,(r->>'cost_return')::float8,
        coalesce(r->>'contract_key',''),r->'option_context') on conflict do nothing;
  end loop;
  update public.market_datasets set cursor=coalesce(p_patch->'cursor',cursor),
    status=coalesce(p_patch->>'status',status),last_error=p_patch->>'last_error',
    first_at=coalesce((p_patch->>'first_at')::timestamptz,first_at),last_at=coalesce((p_patch->>'last_at')::timestamptz,last_at),
    train_end=coalesce((p_patch->>'train_end')::timestamptz,train_end),
    validation_end=coalesce((p_patch->>'validation_end')::timestamptz,validation_end),
    raw_count=coalesce((p_patch->>'raw_count')::int,raw_count),feature_count=coalesce((p_patch->>'feature_count')::int,feature_count),
    training_win_rate=coalesce((p_patch->>'training_win_rate')::float8,training_win_rate),
    lease_token=null,lease_until=null where id=p_id;
end $$;

create or replace function public.match_historical_patterns(p_dataset uuid,p_as_of timestamptz,
  p_reference_end timestamptz,p_embedding extensions.vector(12),p_count integer)
returns table(id bigint,observed_at timestamptz,outcome_at timestamptz,embedding text,
  regime text,net_return double precision,cost_return double precision,contract_key text,distance double precision)
language sql stable security invoker set search_path=public,extensions as $$
  select f.id,f.observed_at,f.outcome_at,f.embedding::text,f.regime,f.net_return,f.cost_return,f.contract_key,
    (f.embedding <-> p_embedding)::float8 from public.historical_features f
  where f.dataset_id=p_dataset and f.observed_at<p_as_of
    and f.outcome_at<least(p_as_of,p_reference_end)
  order by f.embedding <-> p_embedding,f.id limit least(greatest(p_count,1),256);
$$;

create or replace function public.commit_optimizer_work(p_id uuid,p_token uuid,p_work jsonb,
  p_status text,p_result jsonb default null,p_consume_holdout boolean default false)
returns void language plpgsql security invoker set search_path=public as $$
declare j public.ai_optimization_jobs; lock_id uuid;
begin
  select * into j from public.ai_optimization_jobs where id=p_id for update;
  if not found or p_token is null or j.lease_until is null or j.lease_token is distinct from p_token or j.lease_until<=now() or j.status<>'running' then raise exception 'stale_lease'; end if;
  if p_consume_holdout then
    if p_work->>'stage'<>'certification' or p_work->>'run_id' is null then raise exception 'invalid_holdout_lock'; end if;
    select holdout_run_id into lock_id from public.market_datasets where id=j.dataset_id for update;
    if lock_id is not null then raise exception 'holdout_already_consumed'; end if;
    update public.market_datasets set holdout_run_id=(p_work->>'run_id')::uuid where id=j.dataset_id;
  end if;
  if p_result is not null then
    insert into public.ai_optimization_runs(id,job_id,user_id,trial,stage,parameters,metrics,qualified)
      values((p_result->>'id')::uuid,j.id,j.user_id,(p_result->>'trial')::int,p_result->>'stage',
        p_result->'parameters',p_result->'metrics',coalesce((p_result->>'qualified')::boolean,false))
      on conflict(job_id,trial,stage) do nothing;
  end if;
  update public.ai_optimization_jobs set work=p_work,status=p_status,updated_at=now(),
    next_attempt_at=now()+interval '30 seconds',lease_token=null,lease_until=null where id=p_id;
end $$;

revoke all on function public.claim_cloud_work() from public,anon,authenticated;
revoke all on function public.commit_dataset_work(uuid,uuid,jsonb,jsonb,jsonb) from public,anon,authenticated;
revoke all on function public.match_historical_patterns(uuid,timestamptz,timestamptz,extensions.vector,integer) from public,anon,authenticated;
revoke all on function public.commit_optimizer_work(uuid,uuid,jsonb,text,jsonb,boolean) from public,anon,authenticated;
grant execute on function public.claim_cloud_work(), public.commit_dataset_work(uuid,uuid,jsonb,jsonb,jsonb),
 public.match_historical_patterns(uuid,timestamptz,timestamptz,extensions.vector,integer),
 public.commit_optimizer_work(uuid,uuid,jsonb,text,jsonb,boolean) to service_role;

create or replace function public.append_uploaded_features(p_dataset uuid,p_user uuid,p_features jsonb,p_finish boolean)
returns void language plpgsql security invoker set search_path=public,extensions as $$
declare d public.market_datasets; r jsonb; n int; days int; first_time timestamptz; last_time timestamptz; prior timestamptz;
begin
  select * into d from public.market_datasets where id=p_dataset and user_id=p_user for update;
  if not found or d.source<>'upload' or d.status<>'ingesting' then raise exception 'upload_not_writable'; end if;
  if jsonb_array_length(p_features)>500 then raise exception 'batch_limit'; end if;
  prior=d.last_at;
  for r in select * from jsonb_array_elements(p_features) loop
    if prior is not null and (r->>'observed_at')::timestamptz<prior then raise exception 'upload_order'; end if;
    prior=(r->>'observed_at')::timestamptz;
    insert into public.historical_features(dataset_id,user_id,observed_at,outcome_at,embedding,regime,net_return,cost_return,contract_key,option_context)
      values(d.id,p_user,prior,(r->>'outcome_at')::timestamptz,(r->'embedding')::text::extensions.vector,
       r->>'regime',(r->>'net_return')::float8,(r->>'cost_return')::float8,coalesce(r->>'contract_key',''),r->'option_context') on conflict do nothing;
  end loop;
  select count(*),count(distinct observed_at::date),min(observed_at),max(observed_at) into n,days,first_time,last_time
    from public.historical_features where dataset_id=d.id;
  if n>1000000 then raise exception 'dataset_limit'; end if;
  update public.market_datasets set first_at=first_time,last_at=last_time,feature_count=n where id=d.id;
  if p_finish then
    if n<1000 or days<d.requested_years*170 or extract(epoch from last_time-first_time)/31557600<d.requested_years-0.2 then raise exception 'incomplete_history'; end if;
    update public.market_datasets set status='ready',
      train_end=first_time+(last_time-first_time)*0.6,validation_end=first_time+(last_time-first_time)*0.8 where id=d.id;
    update public.market_datasets set training_win_rate=(select avg((net_return>0)::int) from public.historical_features
      where dataset_id=d.id and outcome_at<first_time+(last_time-first_time)*0.6) where id=d.id;
  end if;
end $$;
revoke all on function public.append_uploaded_features(uuid,uuid,jsonb,boolean) from public,anon,authenticated;
grant execute on function public.append_uploaded_features(uuid,uuid,jsonb,boolean) to service_role;

create or replace function public.summarize_market_bars(p_dataset uuid)
returns jsonb language sql stable security invoker set search_path=public as $$
  with ordered as (
    select observed_at,observed_at-lag(observed_at) over(order by observed_at) as gap
    from public.market_bars where dataset_id=p_dataset
  ) select jsonb_build_object('count',count(*),'first_at',min(observed_at),'last_at',max(observed_at),
    'max_gap_seconds',extract(epoch from max(gap)),
    'train_end',percentile_disc(0.6) within group(order by observed_at),
    'validation_end',percentile_disc(0.8) within group(order by observed_at)) from ordered;
$$;
revoke all on function public.summarize_market_bars(uuid) from public,anon,authenticated;
grant execute on function public.summarize_market_bars(uuid) to service_role;

-- Dashboard uses authenticated reads + Realtime; no service key in the browser.
do $$ declare t text; begin
  foreach t in array array['market_datasets','ai_optimization_jobs','ai_optimization_runs','trade_logs','equity_snapshots'] loop
    if not exists(select 1 from pg_publication_tables where pubname='supabase_realtime' and schemaname='public' and tablename=t) then
      execute format('alter publication supabase_realtime add table public.%I',t);
    end if;
  end loop;
end $$;
commit;
