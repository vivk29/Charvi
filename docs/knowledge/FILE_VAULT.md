# Charvi Knowledge File Vault

The `knowledge_files` metadata table is private to the backend: RLS is enabled, direct `anon` and `authenticated` privileges are revoked, and only the server `service_role` receives Data API privileges. A database trigger verifies that the metadata owner owns the referenced workspace.

Original bytes are stored in the private Supabase Storage bucket `charvi-knowledge`. The bucket is not public and is limited to 15 MiB and the supported document, spreadsheet, presentation, text, and image MIME types. The API uploads with its server-only service credential; the browser never receives that credential or a public object URL.

The initial authenticated API routes are:

- `POST /v1/workspaces/{workspace_id}/knowledge-files` — validates a supported extension and file signature, enforces a 15 MiB request limit, uploads the original to a workspace/user/UUID storage path, computes SHA-256, and writes metadata.
- `GET /v1/workspaces/{workspace_id}/knowledge-files` — lists metadata only after verifying workspace ownership.

This milestone stores originals and metadata. It does not yet parse document contents, create embeddings, generate signed download links, or mark files as AI-ready. Those are subsequent milestones. Legacy DOC/XLS/PPT files currently receive an OLE signature check; deeper format validation belongs in the parser sandbox.
