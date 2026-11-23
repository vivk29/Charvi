-- Adds the verified human requester to approval records and audit events.
alter table public.approvals
  add column requested_by_user_id uuid references auth.users(id);

create index approvals_requested_by_user_id_idx
  on public.approvals (requested_by_user_id);

create or replace function private.guard_and_audit_approval()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public
as $function$
begin
  if tg_op = 'INSERT' then
    if new.status <> 'pending' then
      raise exception 'Approval requests must start as pending';
    end if;
    if new.payload_sha256 is null or new.payload_sha256 !~ '^[0-9a-f]{64}$' then
      raise exception 'A valid SHA-256 payload digest is required';
    end if;
    if new.requested_by_user_id is null then
      raise exception 'Approval requester identity is required';
    end if;
    insert into public.approval_decision_events
      (approval_id, workspace_id, event_type, actor_id, payload_sha256, metadata)
    values
      (new.id, new.workspace_id, 'requested', new.requested_by_user_id,
       new.payload_sha256,
       jsonb_build_object('action_type', new.action_type,
                          'action_category', new.action_category,
                          'risk_level', new.risk_level,
                          'title', new.title));
    return new;
  end if;

  if row(new.workspace_id, new.project_id, new.task_id, new.requested_by_agent_id,
         new.requested_by_user_id, new.action_type, new.title, new.description,
         new.payload, new.run_id, new.action_category, new.risk_level,
         new.expires_at, new.payload_sha256, new.approval_nonce, new.created_at)
     is distinct from
     row(old.workspace_id, old.project_id, old.task_id, old.requested_by_agent_id,
         old.requested_by_user_id, old.action_type, old.title, old.description,
         old.payload, old.run_id, old.action_category, old.risk_level,
         old.expires_at, old.payload_sha256, old.approval_nonce, old.created_at) then
    raise exception 'Approval request payload and scope are immutable';
  end if;
  if old.status <> 'pending' then
    raise exception 'A decided approval cannot be changed';
  end if;
  if new.status not in ('approved', 'rejected', 'cancelled') then
    raise exception 'Invalid approval state transition';
  end if;
  if new.decided_by is null then
    raise exception 'A decision actor is required';
  end if;
  if new.status in ('approved', 'rejected') then
    if new.decided_at is null then
      raise exception 'A human decision requires decided_at';
    end if;
    if old.expires_at is not null and new.decided_at > old.expires_at then
      raise exception 'Expired approval requests cannot be decided';
    end if;
  end if;
  insert into public.approval_decision_events
    (approval_id, workspace_id, event_type, actor_id, payload_sha256, metadata)
  values
    (new.id, new.workspace_id, new.status, new.decided_by, new.payload_sha256,
     jsonb_build_object('decision_note', new.decision_note,
                        'action_type', new.action_type,
                        'action_category', new.action_category,
                        'risk_level', new.risk_level));
  return new;
end;
$function$;

revoke all on function private.guard_and_audit_approval()
  from public, anon, authenticated, service_role;
