create table if not exists public.knowledge_chunks (
  id uuid primary key default gen_random_uuid(),
  knowledge_file_id uuid not null references public.knowledge_files(id) on delete cascade,
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  chunk_index integer not null check (chunk_index >= 0),
  content text not null check (char_length(content) between 1 and 2400),
  locator_type text not null,
  locator jsonb not null default '{}'::jsonb,
  content_sha256 text not null check (content_sha256 ~ '^[0-9a-f]{64}$'),
  search_vector tsvector generated always as (to_tsvector('simple', content)) stored,
  created_at timestamptz not null default now(),
  unique (knowledge_file_id, chunk_index)
);
create index if not exists knowledge_chunks_workspace_file_idx
  on public.knowledge_chunks(workspace_id, knowledge_file_id, chunk_index);
create index if not exists knowledge_chunks_search_idx
  on public.knowledge_chunks using gin(search_vector);
alter table public.knowledge_chunks enable row level security;
revoke all on public.knowledge_chunks from public, anon, authenticated;
grant select, insert, update, delete on public.knowledge_chunks to service_role;

create or replace function private.enforce_knowledge_chunk_scope()
returns trigger language plpgsql security definer
set search_path = pg_catalog, public
as $$
declare file_workspace uuid;
begin
  select workspace_id into file_workspace
  from public.knowledge_files where id = new.knowledge_file_id;
  if file_workspace is null or file_workspace <> new.workspace_id then
    raise exception 'knowledge chunk workspace must match its source file'
      using errcode = '23514';
  end if;
  return new;
end;
$$;
revoke all on function private.enforce_knowledge_chunk_scope() from public, anon, authenticated, service_role;
drop trigger if exists enforce_knowledge_chunk_scope on public.knowledge_chunks;
create trigger enforce_knowledge_chunk_scope
before insert or update of knowledge_file_id, workspace_id
on public.knowledge_chunks
for each row execute function private.enforce_knowledge_chunk_scope();
