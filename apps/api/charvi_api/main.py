import hashlib
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID, uuid4

import httpx
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .agents import AgentSettings
from .auth import UserIdentity, get_current_user
from .gateway import GatewayRequest, authorize_gateway_request, payload_digest
from .knowledge import MAX_FILE_BYTES, validate_file
from .document_parser import chunk_units, extract_document
from .memory import (
    build_memory_context,
    is_safe_memory_content,
    normalize_memory_query,
    should_use_saved_memory,
)
from .orchestrator import CharviOrchestrator
from .policy import ActionCategory, ActionRequest, evaluate_action
from .store import SupabaseRestStore, get_store

logger = logging.getLogger(__name__)

CurrentUser = Annotated[UserIdentity, Depends(get_current_user)]
Store = Annotated[SupabaseRestStore, Depends(get_store)]


def get_orchestrator(request: Request) -> CharviOrchestrator:
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        orchestrator = CharviOrchestrator(AgentSettings())
        request.app.state.orchestrator = orchestrator
    return orchestrator


Orchestrator = Annotated[CharviOrchestrator, Depends(get_orchestrator)]


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings = AgentSettings()
    connection = None
    checkpointer = None
    if settings.langgraph_postgres_uri:
        try:
            # Restrict checkpoint deserialization before the saver is initialized.
            os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from psycopg import AsyncConnection
            from psycopg.rows import dict_row

            connection = await AsyncConnection.connect(
                settings.langgraph_postgres_uri,
                autocommit=True,
                prepare_threshold=0,
                row_factory=dict_row,
                options="-c search_path=charvi_memory,public",
            )
            checkpointer = AsyncPostgresSaver(connection)
            await checkpointer.setup()
            for table in (
                "checkpoints",
                "checkpoint_blobs",
                "checkpoint_writes",
                "checkpoint_migrations",
            ):
                await connection.execute(
                    f"ALTER TABLE charvi_memory.{table} ENABLE ROW LEVEL SECURITY"
                )
        except Exception as exc:
            if connection is not None:
                await connection.close()
            raise RuntimeError(
                "LangGraph checkpoint storage was configured but could not be initialized; "
                "Charvi is refusing to start without its requested durable memory."
            ) from exc

    try:
        application.state.orchestrator = CharviOrchestrator(
            settings,
            checkpointer=checkpointer,
        )
        yield
    finally:
        if connection is not None:
            await connection.close()


app = FastAPI(
    title="Charvi Control Plane",
    version="0.5.0",
    description=(
        "Identity, workspace, policy, approvals, audit, durable task history and task-routing API."
    ),
    lifespan=lifespan,
)

allowed_origins = [
    origin.strip()
    for origin in AgentSettings().cors_allowed_origins.split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "apikey"],
)


class VoiceSynthesisInput(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    voice: Literal[
        "af_heart", "af_bella", "af_nicole", "af_aoede", "af_kore",
        "af_sarah", "af_nova", "bf_emma", "bf_isabella", "bf_alice",
        "hf_alpha", "hf_beta",
    ] = "af_heart"


class WorkspaceCreateInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ActionEvaluationInput(BaseModel):
    workspace_id: UUID
    category: ActionCategory
    target: str = Field(min_length=1, max_length=512)
    description: str = Field(min_length=1, max_length=2000)
    reversible: bool = True
    idempotency_key: str = Field(min_length=1, max_length=128)
    payload: dict[str, object] = Field(default_factory=dict)


class ApprovalRequestInput(BaseModel):
    category: ActionCategory
    target: str = Field(min_length=1, max_length=512)
    description: str = Field(min_length=1, max_length=2000)
    reversible: bool = True
    idempotency_key: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    payload: dict[str, object] = Field(default_factory=dict)
    expires_in_minutes: int = Field(default=60, ge=5, le=10080)


class AgentRunInput(BaseModel):
    workspace_id: UUID
    task: str = Field(min_length=1, max_length=12000)
    context: str = Field(default="", max_length=20000)
    thread_id: UUID | None = None
    idempotency_key: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=128)
    approval_id: UUID | None = None
    use_saved_memory: bool = True


class ApprovalDecisionInput(BaseModel):
    decision: Literal["approved", "rejected", "cancelled"]
    note: str | None = Field(default=None, max_length=2000)


class MemoryCreateInput(BaseModel):
    memory_key: str = Field(min_length=1, max_length=160, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=4000)
    memory_type: Literal["preference", "profile", "project", "workflow", "reference"]
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_run_id: UUID | None = None


def risk_for(category: ActionCategory, reversible: bool = False) -> str:
    if category == ActionCategory.WRITE and reversible:
        return "low"
    if category in {ActionCategory.FINANCIAL, ActionCategory.DESTRUCTIVE,
                    ActionCategory.CREDENTIAL_ACCESS}:
        return "critical"
    if category in {ActionCategory.EXTERNAL_MESSAGE, ActionCategory.DEVICE_CONTROL,
                    ActionCategory.DEPLOYMENT}:
        return "high"
    if category == ActionCategory.WRITE:
        return "medium"
    return "low"


async def owned_workspace(store: SupabaseRestStore, workspace_id: UUID, user: UserIdentity):
    workspace = await store.get_workspace(str(workspace_id), user.user_id)
    if workspace is None:
        # Avoid revealing whether another user's workspace exists.
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return workspace


@app.post("/v1/voice/transcribe", tags=["voice"])
async def transcribe_voice(
    file: Annotated[UploadFile, File()],
    user: CurrentUser,
    language: Annotated[Literal["en", "hi", "kn"] | None, Form()] = None,
) -> dict[str, object]:
    """Proxy a short recording to Charvi's private Whisper worker."""
    del user
    settings = AgentSettings()
    if not settings.whisper_worker_url or not settings.whisper_worker_token:
        raise HTTPException(
            status_code=503,
            detail="Private Whisper transcription is not configured.",
        )
    allowed_types = {
        "audio/webm", "audio/ogg", "audio/wav", "audio/x-wav",
        "audio/mpeg", "audio/mp4", "audio/aac", "audio/flac",
    }
    media_type = (file.content_type or "").split(";", maxsplit=1)[0].lower()
    if media_type not in allowed_types:
        raise HTTPException(status_code=415, detail="Unsupported audio format.")
    content = await file.read(20 * 1024 * 1024 + 1)
    if not content:
        raise HTTPException(status_code=400, detail="The audio recording is empty.")
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio must be 20 MB or smaller.")
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.whisper_worker_timeout_seconds)
        ) as client:
            result = await client.post(
                f"{settings.whisper_worker_url.rstrip('/')}/v1/transcribe",
                headers={"X-Charvi-Worker-Token": settings.whisper_worker_token},
                files={
                    "file": (
                        file.filename or "charvi-recording.webm",
                        content,
                        media_type,
                    )
                },
                data={"language": language or ""},
            )
            result.raise_for_status()
            data = result.json()
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Private transcription timed out.") from exc
    except httpx.HTTPStatusError as exc:
        logger.warning("Private Whisper worker returned HTTP %s", exc.response.status_code)
        raise HTTPException(status_code=502, detail="Private transcription failed.") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Private Whisper worker is unavailable.") from exc
    finally:
        await file.close()

    transcript = data.get("text")
    if not isinstance(transcript, str):
        raise HTTPException(status_code=502, detail="Private transcription returned invalid data.")
    return {
        "text": transcript,
        "language": data.get("language"),
        "language_probability": data.get("language_probability"),
        "duration_seconds": data.get("duration_seconds"),
    }


@app.post("/v1/voice/speak", tags=["voice"])
async def synthesize_voice(
    payload: VoiceSynthesisInput,
    user: CurrentUser,
) -> Response:
    """Proxy speech generation through the private, optional Kokoro worker."""
    del user  # A verified Charvi account is required before using the worker.
    settings = AgentSettings()
    if not settings.kokoro_tts_url:
        raise HTTPException(
            status_code=503,
            detail="The private voice engine is not configured; use the browser voice fallback.",
        )
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.kokoro_tts_timeout_seconds)
        ) as client:
            result = await client.post(
                f"{settings.kokoro_tts_url.rstrip('/')}/tts/generate",
                json={
                    "text": payload.text,
                    "voice": payload.voice,
                    "output_format": "mp3",
                },
            )
            result.raise_for_status()
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Voice synthesis timed out.") from exc
    except httpx.HTTPStatusError as exc:
        logger.warning("Private voice worker returned HTTP %s", exc.response.status_code)
        raise HTTPException(status_code=502, detail="Private voice synthesis failed.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Private voice worker is unavailable.") from exc

    if not result.content:
        raise HTTPException(status_code=502, detail="Private voice worker returned empty audio.")
    return Response(
        content=result.content,
        media_type=result.headers.get("content-type", "audio/mpeg"),
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "charvi-control-plane"}


@app.get("/v1/me", tags=["identity"])
async def current_identity(user: CurrentUser) -> dict[str, str | None]:
    return {"user_id": user.user_id, "email": user.email}



@app.post("/v1/workspaces/{workspace_id}/knowledge-files", tags=["knowledge"], status_code=201)
async def upload_knowledge_file(
    workspace_id: UUID,
    file: Annotated[UploadFile, File()],
    user: CurrentUser,
    store: Store,
    department: Annotated[str | None, Form()] = None,
) -> dict[str, object]:
    """Upload one validated file to the private, workspace-scoped knowledge vault."""
    await owned_workspace(store, workspace_id, user)
    content = await file.read(MAX_FILE_BYTES + 1)
    await file.close()
    try:
        validated = validate_file(file.filename or "", content)
    except ValueError as exc:
        message = str(exc)
        status_code = 413 if "15 MB" in message else 415
        raise HTTPException(status_code=status_code, detail=message) from exc

    allowed_departments = {
        "Finance & Treasury", "Accounting & Tax", "Sales & Revenue", "Marketing",
        "Human Resources", "Operations & Supply Chain", "Customer Support",
        "Legal & Compliance", "Projects & IT", "Procurement & Vendors",
        "Strategy & Executive Office",
    }
    selected_department = department.strip() if department else None
    if selected_department and selected_department not in allowed_departments:
        raise HTTPException(status_code=422, detail="Unknown department. Create a custom department first.")

    file_id = uuid4()
    safe_extension = validated.extension
    storage_path = f"{workspace_id}/{user.user_id}/{file_id}.{safe_extension}"
    digest = hashlib.sha256(content).hexdigest()
    await store.upload_knowledge_object(storage_path, content, validated.mime_type)
    try:
        record = await store.create_knowledge_file({
            "id": str(file_id),
            "workspace_id": str(workspace_id),
            "owner_id": user.user_id,
            "original_name": (file.filename or "upload").replace("\\x00", "")[:255],
            "mime_type": validated.mime_type,
            "extension": safe_extension,
            "size_bytes": len(content),
            "sha256": digest,
            "storage_bucket": "charvi-knowledge",
            "storage_path": storage_path,
            "department": selected_department,
            "status": "uploaded",
            "metadata": {"source": "owner_upload", "content_type_header_ignored": True},
        })
    except Exception:
        await store.delete_knowledge_object(storage_path)
        raise
    return record


@app.get("/v1/workspaces/{workspace_id}/knowledge-files", tags=["knowledge"])
async def list_knowledge_files(
    workspace_id: UUID,
    user: CurrentUser,
    store: Store,
) -> list[dict[str, object]]:
    await owned_workspace(store, workspace_id, user)
    return await store.list_knowledge_files(str(workspace_id))


@app.post("/v1/workspaces", tags=["workspaces"], status_code=201)
async def create_workspace(
    payload: WorkspaceCreateInput,
    user: CurrentUser,
    store: Store,
) -> dict[str, object]:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Workspace name cannot be blank.")
    slug_base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48]
    slug = f"{slug_base or 'workspace'}-{uuid4().hex[:8]}"
    return await store.create_workspace({
        "owner_id": user.user_id,
        "name": name,
        "slug": slug,
    })


@app.get("/v1/workspaces", tags=["workspaces"])
async def list_my_workspaces(user: CurrentUser, store: Store) -> list[dict[str, object]]:
    return await store.list_workspaces(user.user_id)


@app.post("/v1/actions/evaluate", tags=["security"])
async def evaluate_action_request(
    payload: ActionEvaluationInput,
    user: CurrentUser,
    store: Store,
) -> dict[str, object]:
    await owned_workspace(store, payload.workspace_id, user)
    request = GatewayRequest(
        workspace_id=str(payload.workspace_id),
        actor_id=user.user_id,
        action=ActionRequest(
            category=payload.category,
            target=payload.target,
            description=payload.description,
            reversible=payload.reversible,
        ),
        idempotency_key=payload.idempotency_key,
        payload=payload.payload,
    )
    decision = authorize_gateway_request(request, now_epoch=int(time.time()))
    return {
        "allowed_to_execute": decision.allowed_to_execute,
        "approval_required": decision.approval_required,
        "payload_sha256": decision.payload_sha256,
        "reason": decision.reason,
        "execution_performed": False,
        "actor_id": user.user_id,
    }


@app.post("/v1/workspaces/{workspace_id}/approvals", tags=["approvals"], status_code=201)
async def create_approval_request(
    workspace_id: UUID,
    payload: ApprovalRequestInput,
    user: CurrentUser,
    store: Store,
) -> dict[str, object]:
    await owned_workspace(store, workspace_id, user)
    action = ActionRequest(payload.category, payload.target, payload.description, payload.reversible)
    policy = evaluate_action(action)
    if not policy.approval_required:
        raise HTTPException(
            status_code=409,
            detail="This action does not need approval under the current policy; Charvi can proceed within its configured scope.",
        )
    request = GatewayRequest(
        workspace_id=str(workspace_id),
        actor_id=user.user_id,
        action=action,
        idempotency_key=payload.idempotency_key,
        payload=payload.payload,
    )
    expires_at = datetime.now(UTC) + timedelta(minutes=payload.expires_in_minutes)
    record = await store.create_approval({
        "workspace_id": str(workspace_id),
        "requested_by_user_id": user.user_id,
        "action_type": payload.category.value,
        "action_category": payload.category.value,
        "risk_level": risk_for(payload.category, payload.reversible),
        "title": payload.title,
        "description": payload.description,
        "payload": {
            **payload.payload,
            "target": payload.target,
            "description": payload.description,
            "reversible": payload.reversible,
            "idempotency_key": payload.idempotency_key,
        },
        "payload_sha256": payload_digest(request),
        "status": "pending",
        "expires_at": expires_at.isoformat(),
    })
    return record


@app.get("/v1/workspaces/{workspace_id}/approvals", tags=["approvals"])
async def list_workspace_approvals(
    workspace_id: UUID,
    user: CurrentUser,
    store: Store,
    status: Literal["pending", "approved", "rejected", "cancelled"] | None = Query(default=None),
) -> list[dict[str, object]]:
    await owned_workspace(store, workspace_id, user)
    records = await store.list_approvals(str(workspace_id))
    return [item for item in records if status is None or item.get("status") == status]


@app.get("/v1/approvals/{approval_id}/events", tags=["approvals"])
async def list_approval_events(
    approval_id: UUID,
    user: CurrentUser,
    store: Store,
) -> list[dict[str, object]]:
    approval = await store.get_approval(str(approval_id))
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    await owned_workspace(store, UUID(approval["workspace_id"]), user)
    return await store.list_approval_events(str(approval_id))


@app.post("/v1/approvals/{approval_id}/decision", tags=["approvals"])
async def decide_approval(
    approval_id: UUID,
    payload: ApprovalDecisionInput,
    user: CurrentUser,
    store: Store,
) -> dict[str, object]:
    approval = await store.get_approval(str(approval_id))
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    await owned_workspace(store, UUID(approval["workspace_id"]), user)
    if approval.get("status") != "pending":
        raise HTTPException(status_code=409, detail="This approval has already been decided.")
    expiry = approval.get("expires_at")
    if expiry and datetime.fromisoformat(expiry) <= datetime.now(UTC):
        raise HTTPException(status_code=409, detail="This approval request has expired.")
    result = await store.decide_approval(
        str(approval_id),
        actor_id=user.user_id,
        status=payload.decision,
        note=payload.note,
        decided_at=datetime.now(UTC).isoformat(),
    )
    if result is None:
        raise HTTPException(status_code=409, detail="Approval was already decided; refresh and try again.")
    return result


@app.post(
    "/v1/workspaces/{workspace_id}/memories",
    tags=["memory"],
    status_code=201,
)
async def save_memory(
    workspace_id: UUID,
    payload: MemoryCreateInput,
    user: CurrentUser,
    store: Store,
) -> dict[str, object]:
    await owned_workspace(store, workspace_id, user)
    if not is_safe_memory_content(payload.title + " " + payload.content):
        raise HTTPException(
            status_code=422,
            detail="Memory cannot contain obvious passwords, API keys or access tokens.",
        )
    if payload.source_run_id is not None:
        source_run = await store.get_agent_run(str(payload.source_run_id))
        if source_run is None or source_run.get("workspace_id") != str(workspace_id):
            raise HTTPException(status_code=404, detail="Source run not found.")
    now = datetime.now(UTC).isoformat()
    return await store.upsert_memory({
        "workspace_id": str(workspace_id),
        "owner_id": user.user_id,
        "memory_key": payload.memory_key,
        "title": payload.title,
        "content": payload.content,
        "memory_type": payload.memory_type,
        "source_run_id": str(payload.source_run_id) if payload.source_run_id else None,
        "source_kind": "explicit_user",
        "confidence": payload.confidence,
        "status": "active",
        "updated_at": now,
    })


@app.get("/v1/workspaces/{workspace_id}/memories", tags=["memory"])
async def list_saved_memories(
    workspace_id: UUID,
    user: CurrentUser,
    store: Store,
) -> list[dict[str, object]]:
    await owned_workspace(store, workspace_id, user)
    return await store.list_memories(str(workspace_id), user.user_id)


@app.get("/v1/workspaces/{workspace_id}/memories/search", tags=["memory"])
async def search_saved_memories(
    workspace_id: UUID,
    user: CurrentUser,
    store: Store,
    q: str = Query(min_length=1, max_length=300),
) -> list[dict[str, object]]:
    await owned_workspace(store, workspace_id, user)
    normalized_query = normalize_memory_query(q)
    if not normalized_query:
        return []
    return await store.search_memories(str(workspace_id), user.user_id, normalized_query)


@app.post(
    "/v1/workspaces/{workspace_id}/memories/{memory_id}/archive",
    tags=["memory"],
)
async def archive_saved_memory(
    workspace_id: UUID,
    memory_id: UUID,
    user: CurrentUser,
    store: Store,
) -> dict[str, object]:
    await owned_workspace(store, workspace_id, user)
    result = await store.archive_memory(
        str(memory_id),
        str(workspace_id),
        user.user_id,
        updated_at=datetime.now(UTC).isoformat(),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Active memory not found.")
    return result


@app.get("/v1/models/status", tags=["models"])
async def coordinator_model_status(
    user: CurrentUser,
    orchestrator: Orchestrator,
) -> dict[str, object]:
    """Report local-model readiness without issuing a billable generation request."""
    return await orchestrator.model_status()


@app.get("/v1/agents", tags=["agents"])
async def list_configured_agents(
    user: CurrentUser,
    orchestrator: Orchestrator,
) -> list[dict[str, object]]:
    return orchestrator.catalog()


def checkpoint_thread_key(user_id: str, workspace_id: str, thread_id: str) -> str:
    """Namespace checkpoint threads by verified owner and workspace."""
    material = f"{user_id}:{workspace_id}:{thread_id}".encode()
    return hashlib.sha256(material).hexdigest()


def format_orchestration_result(result) -> dict[str, object]:
    openhands_invoked = any(
        item.agent_id == "openhands" and item.status == "completed"
        for item in result.specialists
    )
    openclaw_invoked = any(
        item.agent_id == "openclaw" and item.status == "completed"
        for item in result.specialists
    )
    return {
        "status": result.status,
        "routed_to": list(result.routed_to),
        "coordinator": {
            "agent_id": result.coordinator.agent_id,
            "status": result.coordinator.status,
            "output": result.coordinator.output,
            "error": result.coordinator.error,
        },
        "specialists": [
            {
                "agent_id": item.agent_id,
                "status": item.status,
                "output": item.output,
                "error": item.error,
                "execution_performed": item.execution_performed,
            }
            for item in result.specialists
        ],
        "openhands_runtime_invoked": openhands_invoked,
        "code_execution_possible": openhands_invoked,
        "code_execution_performed": None if openhands_invoked else False,
        "device_control_runtime_invoked": openclaw_invoked,
        "device_control_performed": None if openclaw_invoked else False,
        "external_side_effects_performed": None if openclaw_invoked else False,
    }



@app.post("/v1/workspaces/{workspace_id}/knowledge-files/{file_id}/extract", tags=["knowledge"])
async def extract_knowledge_file(
    workspace_id: UUID, file_id: UUID, user: CurrentUser, store: Store,
) -> dict[str, object]:
    """Extract text into provenance-aware chunks; never execute document content."""
    await owned_workspace(store, workspace_id, user)
    record = await store.get_knowledge_file(str(file_id), str(workspace_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Knowledge file not found.")
    if record.get("status") == "processing":
        raise HTTPException(status_code=409, detail="This file is already being processed.")
    await store.update_knowledge_file(
        str(file_id), str(workspace_id),
        {"status": "processing", "extraction_error": None, "updated_at": datetime.now(UTC).isoformat()},
    )
    try:
        original = await store.download_knowledge_object(record["storage_path"])
        units = extract_document(record["extension"], original)
        chunks = chunk_units(units)
        if not chunks:
            raise ValueError("No readable text was found. This may be a scanned or image-only document.")
        await store.replace_knowledge_chunks(str(file_id), str(workspace_id), chunks)
        page_count = max((int(unit.locator.get("page", 0)) for unit in units
                          if unit.locator_type == "page"), default=0)
        sheet_count = len({unit.locator.get("sheet") for unit in units
                           if unit.locator_type == "spreadsheet_row"})
        summary = f"Extracted {len(units)} source units into {len(chunks)} searchable chunks."
        await store.update_knowledge_file(
            str(file_id), str(workspace_id),
            {"status": "ready", "extraction_summary": summary, "page_count": page_count or None,
             "sheet_count": sheet_count or None, "extraction_error": None,
             "updated_at": datetime.now(UTC).isoformat()},
        )
        return {"file_id": str(file_id), "status": "ready", "source_units": len(units),
                "chunks_created": len(chunks), "page_count": page_count, "sheet_count": sheet_count,
                "summary": summary,
                "note": "Document content is treated as untrusted data, never as executable instructions."}
    except (ValueError, UnicodeDecodeError) as exc:
        await store.update_knowledge_file(
            str(file_id), str(workspace_id),
            {"status": "needs_review", "extraction_error": str(exc)[:1000],
             "updated_at": datetime.now(UTC).isoformat()},
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        await store.update_knowledge_file(
            str(file_id), str(workspace_id),
            {"status": "failed", "extraction_error": "Extraction failed.",
             "updated_at": datetime.now(UTC).isoformat()},
        )
        raise


@app.get("/v1/workspaces/{workspace_id}/knowledge-files/{file_id}/chunks", tags=["knowledge"])
async def list_knowledge_file_chunks(
    workspace_id: UUID, file_id: UUID, user: CurrentUser, store: Store,
) -> list[dict[str, object]]:
    await owned_workspace(store, workspace_id, user)
    record = await store.get_knowledge_file(str(file_id), str(workspace_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Knowledge file not found.")
    return await store.list_knowledge_chunks(str(file_id), str(workspace_id))


@app.post("/v1/agent-runs", tags=["agents"])
async def run_agent_task(
    payload: AgentRunInput,
    user: CurrentUser,
    store: Store,
    orchestrator: Orchestrator,
) -> dict[str, object]:
    await owned_workspace(store, payload.workspace_id, user)
    allow_code_execution = False
    allow_device_control = False
    if payload.approval_id is not None:
        approval = await store.get_approval(str(payload.approval_id))
        if approval is None or approval.get("workspace_id") != str(payload.workspace_id):
            raise HTTPException(status_code=404, detail="Approval request not found.")
        if approval.get("status") != "approved":
            raise HTTPException(status_code=409, detail="This agent runtime requires an approved execution request.")
        expiry = approval.get("expires_at")
        if expiry and datetime.fromisoformat(expiry) <= datetime.now(UTC):
            raise HTTPException(status_code=409, detail="Execution approval has expired.")
        approved_payload = approval.get("payload") or {}
        action_category = approval.get("action_category")
        if action_category not in {ActionCategory.WRITE.value, ActionCategory.DEVICE_CONTROL.value}:
            raise HTTPException(status_code=409, detail="Approval category cannot authorize an agent runtime.")
        if approved_payload.get("reversible") is not False:
            raise HTTPException(status_code=409, detail="Agent execution requires an explicitly non-reversible approval.")
        execution_digest = hashlib.sha256(
            f"{payload.task}\0{payload.context}".encode()
        ).hexdigest()
        if approved_payload.get("execution_sha256") != execution_digest:
            raise HTTPException(
                status_code=409,
                detail="Approval does not match this exact task and context. Create a new approval for the revised request.",
            )
        allow_code_execution = action_category == ActionCategory.WRITE.value
        allow_device_control = action_category == ActionCategory.DEVICE_CONTROL.value

    run_context = payload.context
    memory_records: list[dict[str, object]] = []
    normalized_task_query = normalize_memory_query(payload.task)
    if payload.approval_id is None and should_use_saved_memory(
        payload.task, payload.use_saved_memory
    ) and normalized_task_query:
        memory_records = await store.search_memories(
            str(payload.workspace_id),
            user.user_id,
            normalized_task_query,
            limit=5,
        )
        memory_context = build_memory_context(memory_records)
        if memory_context:
            run_context = "\n\n".join(
                part for part in (payload.context, memory_context) if part
            )

    external_thread_id = str(payload.thread_id or uuid4())
    internal_thread_id = checkpoint_thread_key(
        user.user_id, str(payload.workspace_id), external_thread_id
    )
    started_at = datetime.now(UTC).isoformat()
    run_record = await store.create_agent_run({
        "workspace_id": str(payload.workspace_id),
        "requested_by": user.user_id,
        "status": "running",
        "objective": payload.task,
        "input": {
            "task": payload.task,
            "context": run_context,
            "thread_id": external_thread_id,
            "memory_ids": [str(item["id"]) for item in memory_records],
            "approval_id": str(payload.approval_id) if payload.approval_id else None,
        },
        "thread_id": external_thread_id,
        "idempotency_key": payload.idempotency_key,
        "started_at": started_at,
    })
    run_id = str(run_record["id"])
    try:
        result = await orchestrator.run(
            task=payload.task,
            context=run_context,
            allow_code_execution=allow_code_execution,
            allow_device_control=allow_device_control,
            thread_id=internal_thread_id,
        )
        response = format_orchestration_result(result)
        response.update({
            "run_id": run_id,
            "thread_id": external_thread_id,
            "checkpointing_enabled": orchestrator.checkpointing_enabled,
            "memories_used": len(memory_records),
        })
        await store.update_agent_run(
            run_id,
            str(payload.workspace_id),
            status="succeeded" if result.status == "completed" else "failed",
            result=response,
            finished_at=datetime.now(UTC).isoformat(),
        )
        return response
    except Exception as exc:
        try:
            await store.update_agent_run(
                run_id,
                str(payload.workspace_id),
                status="failed",
                error_summary=type(exc).__name__,
                finished_at=datetime.now(UTC).isoformat(),
            )
        except Exception:
            logger.exception("Could not persist the failed state for agent run %s", run_id)
        raise


@app.get("/v1/workspaces/{workspace_id}/agent-runs", tags=["agents"])
async def list_agent_runs(
    workspace_id: UUID,
    user: CurrentUser,
    store: Store,
) -> list[dict[str, object]]:
    await owned_workspace(store, workspace_id, user)
    return await store.list_agent_runs(str(workspace_id))


@app.get(
    "/v1/workspaces/{workspace_id}/threads/{thread_id}/history",
    tags=["agents"],
)
async def get_thread_history(
    workspace_id: UUID,
    thread_id: UUID,
    user: CurrentUser,
    store: Store,
    orchestrator: Orchestrator,
) -> list[dict[str, str]]:
    await owned_workspace(store, workspace_id, user)
    internal_thread_id = checkpoint_thread_key(
        user.user_id, str(workspace_id), str(thread_id)
    )
    try:
        return await orchestrator.get_thread_history(thread_id=internal_thread_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/v1/agent-runs/{run_id}", tags=["agents"])
async def get_agent_run(
    run_id: UUID,
    user: CurrentUser,
    store: Store,
) -> dict[str, object]:
    record = await store.get_agent_run(str(run_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Agent run not found.")
    await owned_workspace(store, UUID(record["workspace_id"]), user)
    return {key: value for key, value in record.items() if key != "input"}


@app.post("/v1/agent-runs/{run_id}/resume", tags=["agents"])
async def resume_agent_run(
    run_id: UUID,
    user: CurrentUser,
    store: Store,
    orchestrator: Orchestrator,
) -> dict[str, object]:
    record = await store.get_agent_run(str(run_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Agent run not found.")
    workspace_id = UUID(record["workspace_id"])
    await owned_workspace(store, workspace_id, user)
    if record.get("status") not in {"running", "failed"}:
        raise HTTPException(status_code=409, detail="Only interrupted or failed runs can be resumed.")
    run_input = record.get("input") or {}
    if run_input.get("approval_id"):
        raise HTTPException(
            status_code=409,
            detail="Approval-bound execution cannot be resumed automatically. Request a fresh approval first.",
        )
    external_thread_id = record.get("thread_id") or run_input.get("thread_id")
    if not external_thread_id:
        raise HTTPException(status_code=409, detail="This run has no saved conversation thread.")
    internal_thread_id = checkpoint_thread_key(
        user.user_id, str(workspace_id), str(external_thread_id)
    )
    try:
        result = await orchestrator.resume(thread_id=internal_thread_id)
        if result is None:
            # If the process stopped before the first checkpoint, restart only this
            # non-approval-bound task from its persisted input.
            result = await orchestrator.run(
                task=run_input.get("task", record.get("objective", "")),
                context=run_input.get("context", ""),
                thread_id=internal_thread_id,
            )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    response = format_orchestration_result(result)
    response.update({
        "run_id": str(run_id),
        "thread_id": str(external_thread_id),
        "checkpointing_enabled": orchestrator.checkpointing_enabled,
        "resumed": True,
    })
    await store.update_agent_run(
        str(run_id),
        str(workspace_id),
        status="succeeded" if result.status == "completed" else "failed",
        result=response,
        finished_at=datetime.now(UTC).isoformat(),
    )
    return response
