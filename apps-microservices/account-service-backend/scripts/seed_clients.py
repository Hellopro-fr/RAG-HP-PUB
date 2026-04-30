import asyncio
import json
import logging
import os
import sys

from app.db.database import close_db, init_db
from app.db.models import OAuthClient
from app.services.client_service import create_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed")


async def seed_from_env() -> None:
    raw = os.environ.get("OAUTH_CLIENTS_SEED_JSON")
    if not raw:
        logger.info("OAUTH_CLIENTS_SEED_JSON not set — nothing to seed")
        return
    items = json.loads(raw)
    for item in items:
        cid = item["client_id"]
        if await OAuthClient.filter(client_id=cid).exists():
            logger.info("client %s already exists — skipping", cid)
            continue
        secret = await create_client(
            client_id=cid,
            name=item["name"],
            redirect_uris=item["redirect_uris"],
            post_logout_redirect_uris=item.get("post_logout_redirect_uris", []),
            skip_consent=item.get("skip_consent", True),
        )
        logger.warning("CREATED client_id=%s — STORE SECRET NOW: %s", cid, secret)


async def main() -> int:
    from app.core.settings import get_settings
    s = get_settings()
    await init_db(s.database_url)
    try:
        await seed_from_env()
    finally:
        await close_db()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
