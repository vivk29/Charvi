import asyncio
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from charvi_api.auth import AuthSettings, verify_supabase_access_token


def test_supabase_auth_returns_verified_identity() -> None:
    user_id = str(uuid4())

    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/auth/v1/user"
            assert request.headers["apikey"] == "sb_publishable_test"
            assert request.headers["authorization"] == "Bearer valid-token"
            return httpx.Response(200, json={"id": user_id, "email": "owner@example.test"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            identity = await verify_supabase_access_token(
                "valid-token",
                settings=AuthSettings(
                    supabase_url="https://project.supabase.co",
                    supabase_publishable_key="sb_publishable_test",
                ),
                client=client,
            )
        assert identity.user_id == user_id
        assert identity.email == "owner@example.test"

    asyncio.run(scenario())


def test_invalid_supabase_token_is_rejected() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"message": "invalid token"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(HTTPException) as error:
                await verify_supabase_access_token(
                    "bad-token",
                    settings=AuthSettings(
                        supabase_url="https://project.supabase.co",
                        supabase_publishable_key="sb_publishable_test",
                    ),
                    client=client,
                )
        assert error.value.status_code == 401

    asyncio.run(scenario())


def test_auth_service_failure_fails_closed() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(HTTPException) as error:
                await verify_supabase_access_token(
                    "token",
                    settings=AuthSettings(
                        supabase_url="https://project.supabase.co",
                        supabase_publishable_key="sb_publishable_test",
                    ),
                    client=client,
                )
        assert error.value.status_code == 503

    asyncio.run(scenario())
