"""Supabase Auth-backed identity verification for the Charvi API.

The API delegates access-token validation to Supabase Auth's /user endpoint.
This works with the project's active signing algorithm without storing a JWT
signing secret in Charvi. Do not trust user_metadata for authorization.
"""
from dataclasses import dataclass
from uuid import UUID

import httpx
from fastapi import Header, HTTPException
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    supabase_url: str = ""
    supabase_publishable_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@dataclass(frozen=True, slots=True)
class UserIdentity:
    user_id: str
    email: str | None = None


async def verify_supabase_access_token(
    token: str,
    *,
    settings: AuthSettings,
    client: httpx.AsyncClient,
) -> UserIdentity:
    """Ask Supabase Auth to validate the bearer token and return its user ID."""
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise HTTPException(status_code=503, detail="Authentication is not configured.")

    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/user"
    try:
        response = await client.get(
            url,
            headers={
                "apikey": settings.supabase_publishable_key,
                "Authorization": f"Bearer {token}",
            },
        )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=503, detail="Authentication service timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Authentication service unavailable.") from exc

    if response.status_code in (401, 403):
        raise HTTPException(status_code=401, detail="Invalid or expired access token.")
    if response.status_code != 200:
        raise HTTPException(status_code=503, detail="Unable to verify access token.")

    try:
        user = response.json()
        user_id = str(UUID(user["id"]))
    except (ValueError, TypeError, KeyError):
        raise HTTPException(status_code=401, detail="Authentication response is invalid.") from None

    email = user.get("email")
    return UserIdentity(user_id=user_id, email=email if isinstance(email, str) else None)


async def get_current_user(
    authorization: str | None = Header(default=None),
) -> UserIdentity:
    """FastAPI dependency; accepts only a Supabase-issued bearer access token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="A bearer access token is required.")

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="A bearer access token is required.")

    settings = AuthSettings()
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
        return await verify_supabase_access_token(token, settings=settings, client=client)
