create table if not exists public.knowledge_files (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  owner_id uuid not null references auth.users(id) on delete cascade,
  original_name text not null check (char_length(original_name) between 1 and 255),
  mime_type text not null,
  extension text not null,
  size_bytes bigint not null check (size_bytes > 0 and size_bytes <= 15728640),
  sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  storage_bucket text not null default 'charvi-knowledge',
  storage_path text not null unique,
  department text,
  status text not null default 'uploaded'
    check (status in ('uploaded','queued','processing','ready','needs_review','failed')),
  extraction_summary text,
  page_count integer check (page_count is null or page_count >= 0),
  sheet_count integer check (sheet_count is null or sheet_count >= 0),
  extraction_error text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists knowledge_files_workspace_created_idx
  on public.knowledge_files(workspace_id, created_at desc);
create index if not exists knowledge_files_workspace_status_idx
  on public.knowledge_files(workspace_id, status);
create index if not exists knowledge_files_workspace_department_idx
  on public.knowledge_files(workspace_id, department);

alter table public.knowledge_files enable row level security;
revoke all on public.knowledge_files from public, anon, authenticated;
grant select, insert, update on public.knowledge_files to service_role;

create or replace function private.enforce_knowledge_file_scope()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare workspace_owner uuid;
begin
  select owner_id into workspace_owner
  from public.workspaces
  where id = new.workspace_id;

  if workspace_owner is null or workspace_owner <> new.owner_id then
    raise exception 'knowledge file owner must own the workspace'
      using errcode = '23514';
  end if;

  if new.storage_bucket <> 'charvi-knowledge' then
    raise exception 'invalid knowledge storage bucket'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

revoke all on function private.enforce_knowledge_file_scope() from public, anon, authenticated, service_role;

drop trigger if exists enforce_knowledge_file_scope on public.knowledge_files;
create trigger enforce_knowledge_file_scope
before insert or update of workspace_id, owner_id, storage_bucket
on public.knowledge_files
for each row execute function private.enforce_knowledge_file_scope();

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'charvi-knowledge',
  'charvi-knowledge',
  false,
  15728640,
  array[
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'application/msword',
    'application/vnd.ms-excel',
    'application/vnd.ms-powerpoint',
    'text/csv',
    'text/plain',
    'image/jpeg',
    'image/png',
    'image/webp'
  ]
)
on conflict (id) do update set
  public = false,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;
