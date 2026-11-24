"""Server-only Supabase Data API access for the Charvi control plane."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import HTTPException
from pydantic_settings import BaseSettings, SettingsConfigDict


class StoreSettings(BaseSettings):
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class SupabaseRestStore:
    """Minimal privileged store. The service-role credential never leaves the API."""

    def __init__(self, settings: StoreSettings | None = None) -> None:
        self.settings = settings or StoreSettings()

    def _headers(self, *, prefer: str | None = None) -> dict[str, str]:
        if not self.settings.supabase_url or not self.settings.supabase_service_role_key:
            raise HTTPException(
                status_code=503,
                detail="Charvi's private database connection is not configured.",
            )
        headers = {
            "apikey": self.settings.supabase_service_role_key,
            "Authorization": f"Bearer {self.settings.supabase_service_role_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    async def _request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        prefer: str | None = None,
    ) -> list[dict[str, Any]]:
        url = f"{self.settings.supabase_url.rstrip('/')}/rest/v1/{quote(table)}"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as client:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    json=body,
                    headers=self._headers(prefer=prefer),
                )
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail="Charvi's database is unavailable.") from exc

        if response.status_code in (401, 403):
            raise HTTPException(status_code=503, detail="Charvi's private database credential was rejected.")
        if response.status_code == 409:
            raise HTTPException(status_code=409, detail="This request conflicts with an existing record.")
        if response.status_code >= 500:
            raise HTTPException(status_code=503, detail="Charvi's database is temporarily unavailable.")
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail="The database rejected the requested operation.")
        if not response.content:
            return []
        try:
            data = response.json()
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="The database returned an invalid response.") from exc
        return data if isinstance(data, list) else []

    async def create_workspace(self, record: dict[str, Any]) -> dict[str, Any]:
        rows = await self._request(
            "POST", "workspaces",
            params={"select": "id,name,slug,created_at,updated_at"},
            body=record,
            prefer="return=representation",
        )
        if not rows:
            raise HTTPException(status_code=502, detail="The workspace was not created.")
        return rows[0]

    async def list_workspaces(self, owner_id: str) -> list[dict[str, Any]]:
        return await self._request(
            "GET", "workspaces",
            params={
                "select": "id,name,slug,created_at,updated_at",
                "owner_id": f"eq.{owner_id}",
                "order": "created_at.asc",
            },
        )

    async def get_workspace(self, workspace_id: str, owner_id: str) -> dict[str, Any] | None:
        rows = await self._request(
            "GET", "workspaces",
            params={
                "select": "id,name,slug,owner_id",
                "id": f"eq.{workspace_id}",
                "owner_id": f"eq.{owner_id}",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    async def create_agent_run(self, record: dict[str, Any]) -> dict[str, Any]:
        rows = await self._request(
            "POST", "agent_runs",
            params={"select": "*"},
            body=record,
            prefer="return=representation",
        )
        if not rows:
            raise HTTPException(status_code=502, detail="The agent run was not persisted.")
        return rows[0]

    async def get_agent_run(self, run_id: str) -> dict[str, Any] | None:
        rows = await self._request(
            "GET", "agent_runs",
            params={"select": "*", "id": f"eq.{run_id}", "limit": "1"},
        )
        return rows[0] if rows else None

    async def list_agent_runs(self, workspace_id: str) -> list[dict[str, Any]]:
        return await self._request(
            "GET", "agent_runs",
            params={
                "select": "id,workspace_id,thread_id,status,objective,result,error_summary,started_at,finished_at,created_at,updated_at",
                "workspace_id": f"eq.{workspace_id}",
                "order": "created_at.desc",
                "limit": "50",
            },
        )

    async def update_agent_run(
        self,
        run_id: str,
        workspace_id: str,
        *,
        status: str,
        result: dict[str, Any] | None = None,
        error_summary: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
    ) -> dict[str, Any] | None:
        body: dict[str, Any] = {
            "status": status,
            "updated_at": datetime.now(UTC).isoformat(),
            "error_summary": error_summary,
        }
        if result is not None:
            body["result"] = result
        if started_at is not None:
            body["started_at"] = started_at
        if finished_at is not None:
            body["finished_at"] = finished_at
        rows = await self._request(
            "PATCH", "agent_runs",
            params={
                "id": f"eq.{run_id}",
                "workspace_id": f"eq.{workspace_id}",
                "select": "*",
            },
            body=body,
            prefer="return=representation",
        )
        return rows[0] if rows else None

    async def upsert_memory(self, record: dict[str, Any]) -> dict[str, Any]:
        rows = await self._request(
            "POST", "user_memories",
            params={
                "on_conflict": "workspace_id,memory_key",
                "select": "id,workspace_id,owner_id,memory_key,title,content,memory_type,source_run_id,confidence,status,created_at,updated_at",
            },
            body=record,
            prefer="resolution=merge-duplicates,return=representation",
        )
        if not rows:
            raise HTTPException(status_code=502, detail="The memory was not saved.")
        return rows[0]

    async def list_memories(self, workspace_id: str, owner_id: str) -> list[dict[str, Any]]:
        return await self._request(
            "GET", "user_memories",
            params={
                "select": "id,memory_key,title,content,memory_type,source_run_id,confidence,status,created_at,updated_at",
                "workspace_id": f"eq.{workspace_id}",
                "owner_id": f"eq.{owner_id}",
                "status": "eq.active",
                "order": "updated_at.desc",
                "limit": "100",
            },
        )

    async def search_memories(
        self,
        workspace_id: str,
        owner_id: str,
        query: str,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        return await self._request(
            "GET", "user_memories",
            params={
                "select": "id,memory_key,title,content,memory_type,confidence",
                "workspace_id": f"eq.{workspace_id}",
                "owner_id": f"eq.{owner_id}",
                "status": "eq.active",
                "search_vector": f"wfts.{query}",
                "order": "updated_at.desc",
                "limit": str(max(1, min(limit, 10))),
            },
        )

    async def archive_memory(
        self,
        memory_id: str,
        workspace_id: str,
        owner_id: str,
        *,
        updated_at: str,
    ) -> dict[str, Any] | None:
        rows = await self._request(
            "PATCH", "user_memories",
            params={
                "id": f"eq.{memory_id}",
                "workspace_id": f"eq.{workspace_id}",
                "owner_id": f"eq.{owner_id}",
                "status": "eq.active",
                "select": "id,workspace_id,memory_key,title,status,updated_at",
            },
            body={"status": "archived", "updated_at": updated_at},
            prefer="return=representation",
        )
        return rows[0] if rows else None

    async def create_approval(self, record: dict[str, Any]) -> dict[str, Any]:
        rows = await self._request(
            "POST", "approvals",
            params={"select": "*"},
            body=record,
            prefer="return=representation",
        )
        if not rows:
            raise HTTPException(status_code=502, detail="The approval request was not persisted.")
        return rows[0]

    async def list_approvals(self, workspace_id: str) -> list[dict[str, Any]]:
        return await self._request(
            "GET", "approvals",
            params={
                "select": "id,workspace_id,action_type,action_category,title,description,payload,status,risk_level,expires_at,created_at,decided_by,decided_at,decision_note,payload_sha256,approval_nonce",
                "workspace_id": f"eq.{workspace_id}",
                "order": "created_at.desc",
                "limit": "100",
            },
        )

    async def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        rows = await self._request(
            "GET", "approvals",
            params={"select": "*", "id": f"eq.{approval_id}", "limit": "1"},
        )
        return rows[0] if rows else None

    async def decide_approval(
        self,
        approval_id: str,
        *,
        actor_id: str,
        status: str,
        note: str | None,
        decided_at: str,
    ) -> dict[str, Any] | None:
        rows = await self._request(
            "PATCH", "approvals",
            params={"id": f"eq.{approval_id}", "status": "eq.pending", "select": "*"},
            body={
                "status": status,
                "decided_by": actor_id,
                "decided_at": decided_at if status != "cancelled" else None,
                "decision_note": note,
            },
            prefer="return=representation",
        )
        return rows[0] if rows else None

    async def list_approval_events(self, approval_id: str) -> list[dict[str, Any]]:
        return await self._request(
            "GET", "approval_decision_events",
            params={
                "select": "id,approval_id,event_type,actor_id,payload_sha256,metadata,created_at",
                "approval_id": f"eq.{approval_id}",
                "order": "created_at.asc",
                "limit": "100",
            },
        )


    async def upload_knowledge_object(self, path: str, content: bytes, mime_type: str) -> None:
        if not self.settings.supabase_url or not self.settings.supabase_service_role_key:
            raise HTTPException(status_code=503, detail="Charvi's private storage is not configured.")
        url = f"{self.settings.supabase_url.rstrip('/')}/storage/v1/object/charvi-knowledge/{quote(path, safe='/')}"
        headers = {
            "apikey": self.settings.supabase_service_role_key,
            "Authorization": f"Bearer {self.settings.supabase_service_role_key}",
            "Content-Type": mime_type,
            "x-upsert": "false",
            "Cache-Control": "private, max-age=0",
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(45.0)) as client:
                response = await client.post(url, content=content, headers=headers)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail="Private file storage is unavailable.") from exc
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail="Private file storage rejected the upload.")

    async def delete_knowledge_object(self, path: str) -> None:
        if not self.settings.supabase_url or not self.settings.supabase_service_role_key:
            return
        url = f"{self.settings.supabase_url.rstrip('/')}/storage/v1/object/charvi-knowledge/{quote(path, safe='/')}"
        headers = {
            "apikey": self.settings.supabase_service_role_key,
            "Authorization": f"Bearer {self.settings.supabase_service_role_key}",
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
                await client.delete(url, headers=headers)
        except httpx.HTTPError:
            # Orphan cleanup is best-effort; the failed metadata write remains visible to operators.
            return

    async def create_knowledge_file(self, record: dict[str, Any]) -> dict[str, Any]:
        rows = await self._request(
            "POST", "knowledge_files",
            params={"select": "id,workspace_id,original_name,mime_type,extension,size_bytes,sha256,department,status,created_at"},
            body=record,
            prefer="return=representation",
        )
        if not rows:
            raise HTTPException(status_code=502, detail="File metadata was not saved.")
        return rows[0]

    async def list_knowledge_files(self, workspace_id: str) -> list[dict[str, Any]]:
        return await self._request(
            "GET", "knowledge_files",
            params={
                "select": "id,workspace_id,original_name,mime_type,extension,size_bytes,sha256,department,status,extraction_summary,page_count,sheet_count,extraction_error,created_at,updated_at",
                "workspace_id": f"eq.{workspace_id}",
                "order": "created_at.desc",
                "limit": "100",
            },
        )


    async def get_knowledge_file(self, file_id: str, workspace_id: str) -> dict[str, Any] | None:
        rows = await self._request(
            "GET", "knowledge_files",
            params={"select": "id,workspace_id,owner_id,original_name,extension,storage_path,status",
                    "id": f"eq.{file_id}", "workspace_id": f"eq.{workspace_id}", "limit": "1"},
        )
        return rows[0] if rows else None

    async def download_knowledge_object(self, path: str) -> bytes:
        if not self.settings.supabase_url or not self.settings.supabase_service_role_key:
            raise HTTPException(status_code=503, detail="Charvi's private storage is not configured.")
        url = f"{self.settings.supabase_url.rstrip('/')}/storage/v1/object/charvi-knowledge/{quote(path, safe='/')}"
        headers = {"apikey": self.settings.supabase_service_role_key,
                   "Authorization": f"Bearer {self.settings.supabase_service_role_key}"}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
                response = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail="Private file storage is unavailable.") from exc
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="The stored original file is missing.")
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail="Private file storage could not return the original.")
        return response.content

    async def replace_knowledge_chunks(
        self, file_id: str, workspace_id: str, chunks: list[dict[str, Any]]
    ) -> None:
        await self._request("DELETE", "knowledge_chunks",
                            params={"knowledge_file_id": f"eq.{file_id}", "workspace_id": f"eq.{workspace_id}"})
        if chunks:
            records = [{"knowledge_file_id": file_id, "workspace_id": workspace_id,
                        "chunk_index": index, **chunk} for index, chunk in enumerate(chunks)]
            await self._request("POST", "knowledge_chunks", body=records, prefer="return=minimal")

    async def update_knowledge_file(
        self, file_id: str, workspace_id: str, changes: dict[str, Any]
    ) -> None:
        await self._request("PATCH", "knowledge_files",
                            params={"id": f"eq.{file_id}", "workspace_id": f"eq.{workspace_id}"},
                            body=changes, prefer="return=minimal")

    async def search_knowledge_chunks(
        self, workspace_id: str, query: str, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        return await self._request(
            "GET", "knowledge_chunks",
            params={
                "select": "id,knowledge_file_id,chunk_index,content,locator_type,locator,content_sha256",
                "workspace_id": f"eq.{workspace_id}",
                "search_vector": f"fts.{query}",
                "order": "chunk_index.asc",
                "limit": str(max(1, min(limit, 50))),
            },
        )

    async def list_knowledge_chunks(
        self, file_id: str, workspace_id: str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        return await self._request(
            "GET", "knowledge_chunks",
            params={"select": "id,chunk_index,content,locator_type,locator,content_sha256",
                    "knowledge_file_id": f"eq.{file_id}", "workspace_id": f"eq.{workspace_id}",
                    "order": "chunk_index.asc", "limit": str(max(1, min(limit, 200)))},
        )


def get_store() -> SupabaseRestStore:
    return SupabaseRestStore()
