-- Run AFTER schema.sql in a disposable Supabase project, using SQL Editor.
-- Uses synthetic users and rolls back every change. Not a concurrency test.
begin;
do $$ begin
  if not public.consume_research_bridge_nonce('90000000-0000-4000-8000-000000000001') then raise exception 'First bridge nonce rejected'; end if;
  if public.consume_research_bridge_nonce('90000000-0000-4000-8000-000000000001') then raise exception 'Bridge replay accepted'; end if;
end $$;
insert into auth.users(id,email) values
 ('10000000-0000-4000-8000-000000000001','cloud-test-a@example.invalid'),
 ('10000000-0000-4000-8000-000000000002','cloud-test-b@example.invalid');
insert into public.profiles(id,role) values
 ('10000000-0000-4000-8000-000000000001','operator'),
 ('10000000-0000-4000-8000-000000000002','researcher');
insert into public.market_datasets(id,user_id,symbol,requested_years,source,status) values
 ('20000000-0000-4000-8000-000000000001','10000000-0000-4000-8000-000000000001','SPY',20,'upload','ready'),
 ('20000000-0000-4000-8000-000000000002','10000000-0000-4000-8000-000000000002','QQQ',20,'upload','ready');

set local role authenticated;
select set_config('request.jwt.claim.sub','10000000-0000-4000-8000-000000000001',true);
do $$ begin
  if (select count(*) from public.market_datasets)<>1 then raise exception 'RLS tenant isolation failed'; end if;
  if exists(select 1 from public.profiles where id='10000000-0000-4000-8000-000000000002') then raise exception 'Profile isolation failed'; end if;
  begin
    update public.profiles set role='admin' where id=auth.uid();
    raise exception 'Browser could update privileged roles';
  exception when insufficient_privilege then null; end;
  begin
    perform public.claim_cloud_work();
    raise exception 'Browser could invoke worker RPC';
  exception when insufficient_privilege then null; end;
end $$;
reset role;

insert into public.ai_optimization_jobs(id,user_id,dataset_id,status,lease_token,lease_until) values
 ('30000000-0000-4000-8000-000000000001','10000000-0000-4000-8000-000000000001',
  '20000000-0000-4000-8000-000000000001','running','40000000-0000-4000-8000-000000000001',now()+interval '90 seconds');
do $$ declare rejected boolean:=false; begin
  begin
    perform public.commit_optimizer_work('30000000-0000-4000-8000-000000000001',null,'{}','running');
  exception when others then
    if sqlerrm<>'stale_lease' then raise; end if; rejected:=true;
  end;
  if not rejected then raise exception 'Null fencing token accepted'; end if;
end $$;
update public.ai_optimization_jobs set lease_until=now()-interval '1 second'
where id='30000000-0000-4000-8000-000000000001';
do $$ declare rejected boolean:=false; begin
  begin
    perform public.commit_optimizer_work('30000000-0000-4000-8000-000000000001',
      '40000000-0000-4000-8000-000000000001','{}','running');
  exception when others then
    if sqlerrm<>'stale_lease' then raise; end if; rejected:=true;
  end;
  if not rejected then raise exception 'Expired lease accepted'; end if;
end $$;
update public.ai_optimization_jobs set lease_until=now()+interval '90 seconds'
where id='30000000-0000-4000-8000-000000000001';
select public.commit_optimizer_work('30000000-0000-4000-8000-000000000001',
 '40000000-0000-4000-8000-000000000001',
 '{"stage":"certification","run_id":"50000000-0000-4000-8000-000000000001"}','running',null,true);
do $$ begin
  if (select holdout_run_id from public.market_datasets where id='20000000-0000-4000-8000-000000000001')
    is distinct from '50000000-0000-4000-8000-000000000001'::uuid then raise exception 'Holdout was not atomically locked'; end if;
end $$;
update public.ai_optimization_jobs set lease_token='40000000-0000-4000-8000-000000000002',lease_until=now()+interval '90 seconds'
where id='30000000-0000-4000-8000-000000000001';
do $$ declare rejected boolean:=false; begin
  begin
    perform public.commit_optimizer_work('30000000-0000-4000-8000-000000000001',
      '40000000-0000-4000-8000-000000000002',
      '{"stage":"certification","run_id":"50000000-0000-4000-8000-000000000002"}','running',null,true);
  exception when others then
    if sqlerrm<>'holdout_already_consumed' then raise; end if; rejected:=true;
  end;
  if not rejected then raise exception 'Final holdout consumed twice'; end if;
end $$;
rollback;
