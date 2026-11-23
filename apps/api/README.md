# Workspace ownership and approval API

The API now verifies a Supabase Auth bearer token, derives the actor ID from the verified identity, and checks that the actor owns a workspace before accessing its approvals.

## End-user flow

- Charvi performs low-impact read and draft work without creating an approval request.
- For a policy-gated action, Charvi creates a pending approval bound to the exact request digest, workspace, requester and expiry.
- The owner can list pending requests, inspect the audit events, and approve, reject or cancel a request.
- Decisions are recorded by the database trigger in `approval_decision_events`.
- A decision is not an execution event. No external action is executed by these endpoints.

## Routes

- `GET /v1/workspaces`
- `GET /v1/workspaces/{workspace_id}/approvals`
- `POST /v1/workspaces/{workspace_id}/approvals`
- `POST /v1/approvals/{approval_id}/decision`
- `GET /v1/approvals/{approval_id}/events`

## Server configuration

Set `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, and `SUPABASE_SERVICE_ROLE_KEY` in the API's private environment. The service-role key is server-only and must never be committed or exposed to clients. `.env.example` contains placeholders only.

The service-role credential bypasses RLS, so the API explicitly filters workspaces by both the requested workspace ID and the verified owner's user ID. Keep the credential restricted to this API process.

## Important limitations

This milestone does not implement action execution, a user-facing approval inbox, workspace creation, workspace membership/invitations, notifications, or deployment. The existing single-owner workspace model is enforced. Approval decisions only update the approval record and audit trail.
