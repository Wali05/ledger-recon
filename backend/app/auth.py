"""Optional API-key authentication that also identifies the reviewer.

Configure ``API_KEYS`` as comma-separated ``reviewer:key`` pairs, for example
``API_KEYS=alice:3f9c...,bob:a71e...``. When it is unset the API runs in local
mode: every request is accepted and recorded as reviewer ``local``.

Keys are compared as SHA-256 digests with ``hmac.compare_digest`` so lookups do
not leak key length or prefix timing. This is shared-secret access control for a
small review team, not a substitute for SSO or per-tenant isolation.
"""

import hashlib
import hmac
import os
import re

from fastapi import Header, HTTPException

LOCAL_REVIEWER = "local"
_NAME = re.compile(r"^[A-Za-z0-9 ._@-]{1,120}$")


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


def load_keys(raw: str | None = None) -> dict[bytes, str]:
    raw = os.getenv("API_KEYS", "") if raw is None else raw
    keys: dict[bytes, str] = {}
    for entry in filter(None, (part.strip() for part in raw.split(","))):
        reviewer, separator, key = entry.partition(":")
        reviewer, key = reviewer.strip(), key.strip()
        if not separator or not _NAME.fullmatch(reviewer) or len(key) < 16:
            raise ValueError(
                "API_KEYS entries must look like reviewer:key, with a key of at least 16 characters"
            )
        keys[_digest(key)] = reviewer
    return keys


def auth_required() -> bool:
    return bool(load_keys())


async def require_reviewer(authorization: str | None = Header(default=None)) -> str:
    keys = load_keys()
    if not keys:
        return LOCAL_REVIEWER
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() == "bearer" and token:
        presented = _digest(token.strip())
        for digest, reviewer in keys.items():
            if hmac.compare_digest(presented, digest):
                return reviewer
    raise HTTPException(401, "A valid API key is required", headers={"WWW-Authenticate": "Bearer"})
