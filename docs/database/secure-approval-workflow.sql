-- Applied to the connected Charvi Supabase project on 2026-11-23.
-- This is a schema snapshot for review; it is not an automatically executed migration.

ALTER TABLE public.approvals
  ADD COLUMN payload_sha256 text NOT NULL
    CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
  ADD COLUMN approval_nonce uuid NOT NULL DEFAULT gen_random_uuid(),
  ADD CONSTRAINT approvals_approval_nonce_unique UNIQUE (approval_nonce);

CREATE SCHEMA IF NOT EXISTS private;
REVOKE ALL ON SCHEMA private FROM PUBLIC, anon, authenticated, service_role;

CREATE TABLE public.approval_decision_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  approval_id uuid NOT NULL REFERENCES public.approvals(id) ON DELETE RESTRICT,
  workspace_id uuid NOT NULL REFERENCES public.workspaces(id) ON DELETE RESTRICT,
  event_type text NOT NULL CHECK (event_type IN ('requested', 'approved', 'rejected', 'cancelled')),
  actor_id uuid NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
  payload_sha256 text NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.approval_decision_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.approval_decision_events FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.approval_decision_events TO service_role;

CREATE INDEX approval_decision_events_approval_created_idx
  ON public.approval_decision_events (approval_id, created_at);

CREATE POLICY approval_decision_events_backend_read
ON public.approval_decision_events
FOR SELECT TO service_role
USING (true);

CREATE OR REPLACE FUNCTION private.guard_and_audit_approval()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'pending' THEN
      RAISE EXCEPTION 'Approval requests must start as pending';
    END IF;
    IF NEW.payload_sha256 IS NULL OR NEW.payload_sha256 !~ '^[0-9a-f]{64}$' THEN
      RAISE EXCEPTION 'A valid SHA-256 payload digest is required';
    END IF;

    INSERT INTO public.approval_decision_events
      (approval_id, workspace_id, event_type, actor_id, payload_sha256, metadata)
    VALUES
      (NEW.id, NEW.workspace_id, 'requested', NULL, NEW.payload_sha256,
       jsonb_build_object('action_type', NEW.action_type,
                          'action_category', NEW.action_category,
                          'risk_level', NEW.risk_level,
                          'title', NEW.title));
    RETURN NEW;
  END IF;

  IF ROW(NEW.workspace_id, NEW.project_id, NEW.task_id, NEW.requested_by_agent_id,
         NEW.action_type, NEW.title, NEW.description, NEW.payload, NEW.run_id,
         NEW.action_category, NEW.risk_level, NEW.expires_at, NEW.payload_sha256,
         NEW.approval_nonce, NEW.created_at)
     IS DISTINCT FROM
     ROW(OLD.workspace_id, OLD.project_id, OLD.task_id, OLD.requested_by_agent_id,
         OLD.action_type, OLD.title, OLD.description, OLD.payload, OLD.run_id,
         OLD.action_category, OLD.risk_level, OLD.expires_at, OLD.payload_sha256,
         OLD.approval_nonce, OLD.created_at) THEN
    RAISE EXCEPTION 'Approval request payload and scope are immutable';
  END IF;

  IF OLD.status <> 'pending' THEN
    RAISE EXCEPTION 'A decided approval cannot be changed';
  END IF;

  IF NEW.status NOT IN ('approved', 'rejected', 'cancelled') THEN
    RAISE EXCEPTION 'Invalid approval state transition';
  END IF;

  IF NEW.status IN ('approved', 'rejected') THEN
    IF NEW.decided_by IS NULL OR NEW.decided_at IS NULL THEN
      RAISE EXCEPTION 'A human decision requires decided_by and decided_at';
    END IF;
    IF OLD.expires_at IS NOT NULL AND NEW.decided_at > OLD.expires_at THEN
      RAISE EXCEPTION 'Expired approval requests cannot be decided';
    END IF;
  END IF;

  INSERT INTO public.approval_decision_events
    (approval_id, workspace_id, event_type, actor_id, payload_sha256, metadata)
  VALUES
    (NEW.id, NEW.workspace_id, NEW.status, NEW.decided_by, NEW.payload_sha256,
     jsonb_build_object('decision_note', NEW.decision_note,
                        'action_type', NEW.action_type,
                        'action_category', NEW.action_category,
                        'risk_level', NEW.risk_level));

  RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION private.guard_and_audit_approval() FROM PUBLIC, anon, authenticated, service_role;

CREATE TRIGGER approvals_guard_and_audit
BEFORE INSERT OR UPDATE ON public.approvals
FOR EACH ROW EXECUTE FUNCTION private.guard_and_audit_approval();
