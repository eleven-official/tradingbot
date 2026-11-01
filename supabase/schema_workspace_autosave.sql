-- Atomic owner-scoped partial updates. Only the Loki server can call this RPC.
begin;
create or replace function public.merge_member_workspace(
  p_user_id uuid, p_items jsonb, p_removed text[] default array[]::text[]
) returns table(updated_at timestamptz)
language sql security invoker set search_path = public
as $$
  insert into public.member_workspace as workspace(user_id, items, updated_at)
  values (p_user_id, p_items - p_removed, now())
  on conflict (user_id) do update set
    items = (workspace.items || excluded.items) - p_removed,
    updated_at = now()
  returning workspace.updated_at;
$$;
revoke all on function public.merge_member_workspace(uuid, jsonb, text[]) from public, anon, authenticated;
grant execute on function public.merge_member_workspace(uuid, jsonb, text[]) to service_role;
notify pgrst, 'reload schema';
commit;
