create schema if not exists charvi_memory authorization postgres;

revoke all on schema charvi_memory from public, anon, authenticated, service_role;
grant usage, create on schema charvi_memory to postgres;

alter default privileges for role postgres in schema charvi_memory
  revoke all on tables from public, anon, authenticated, service_role;
alter default privileges for role postgres in schema charvi_memory
  revoke all on sequences from public, anon, authenticated, service_role;
alter default privileges for role postgres in schema charvi_memory
  revoke execute on functions from public, anon, authenticated, service_role;

alter table public.agent_runs
  add column if not exists thread_id text;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.agent_runs'::regclass
      and conname = 'agent_runs_thread_id_length_check'
  ) then
    alter table public.agent_runs
      add constraint agent_runs_thread_id_length_check
      check (thread_id is null or char_length(thread_id) between 1 and 128);
  end if;
end
$$;

create index if not exists agent_runs_workspace_thread_created_idx
  on public.agent_runs (workspace_id, thread_id, created_at desc)
  where thread_id is not null;
