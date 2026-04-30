import logging

import httpx

logger = logging.getLogger("hellopro_client")


class HelloProAuthError(Exception):
    """Upstream rejected credentials."""


class HelloProUnavailable(Exception):
    """Upstream unreachable / 5xx after retry."""


async def validate_credentials(
    email: str, password: str, url: str, *, timeout: float
) -> dict:
    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(2):
            try:
                r = await client.post(url, json={"email": email, "password": password})
            except (httpx.TransportError, httpx.TimeoutException) as e:
                last_exc = e
                continue
            if r.status_code == 200:
                data = r.json()
                return {
                    "sub": data.get("sub") or data.get("email") or email,
                    "email": data.get("email", email),
                    "display_name": data.get("display_name", ""),
                }
            if r.status_code in (401, 403):
                raise HelloProAuthError("invalid credentials")
            if 500 <= r.status_code < 600:
                last_exc = RuntimeError(f"upstream {r.status_code}")
                continue
            raise HelloProUnavailable(f"unexpected status {r.status_code}")
    raise HelloProUnavailable(str(last_exc) if last_exc else "unknown")
