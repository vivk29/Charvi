create index approval_decision_events_actor_id_idx
  on public.approval_decision_events (actor_id);

create index approval_decision_events_workspace_id_idx
  on public.approval_decision_events (workspace_id);
