create table public.user_memories (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    owner_id uuid not null references auth.users(id) on delete cascade,
    memory_key text not null check (char_length(memory_key) between 1 and 160),
    title text not null check (char_length(title) between 1 and 160),
    content text not null check (char_length(content) between 1 and 4000),
    memory_type text not null check (
        memory_type in ('preference', 'profile', 'project', 'workflow', 'reference')
    ),
    source_run_id uuid references public.agent_runs(id) on delete set null,
    source_kind text not null default 'explicit_user'
        check (source_kind = 'explicit_user'),
    confidence numeric(4,3) not null default 1.000
        check (confidence >= 0 and confidence <= 1),
    status text not null default 'active'
        check (status in ('active', 'archived')),
    search_vector tsvector generated always as (
        to_tsvector('english', coalesce(title, '') || ' ' || content)
    ) stored,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (workspace_id, memory_key)
);

alter table public.user_memories enable row level security;

revoke all on table public.user_memories from public, anon, authenticated;
grant select, insert, update on table public.user_memories to service_role;

create index user_memories_workspace_status_updated_idx
    on public.user_memories (workspace_id, status, updated_at desc);
create index user_memories_search_vector_idx
    on public.user_memories using gin (search_vector);
create index user_memories_owner_workspace_idx
    on public.user_memories (owner_id, workspace_id);

create policy "Backend service role manages owner-scoped memories"
on public.user_memories
for all
to service_role
using (true)
with check (true);

revoke all on table public.user_memories from service_role;
grant select, insert, update on table public.user_memories to service_role;

create or replace function private.enforce_user_memory_scope()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
    workspace_owner uuid;
begin
    select w.owner_id
      into workspace_owner
      from public.workspaces w
     where w.id = new.workspace_id;

    if workspace_owner is null or workspace_owner is distinct from new.owner_id then
        raise exception 'Memory owner must match the workspace owner'
            using errcode = '23514';
    end if;

    if new.source_run_id is not null and not exists (
        select 1
          from public.agent_runs r
         where r.id = new.source_run_id
           and r.workspace_id = new.workspace_id
    ) then
        raise exception 'Memory source run must belong to the same workspace'
            using errcode = '23514';
    end if;

    return new;
end;
$$;

revoke all on function private.enforce_user_memory_scope() from public, anon, authenticated, service_role;

drop trigger if exists enforce_user_memory_scope on public.user_memories;
create trigger enforce_user_memory_scope
before insert or update of workspace_id, owner_id, source_run_id
on public.user_memories
for each row
execute function private.enforce_user_memory_scope();
