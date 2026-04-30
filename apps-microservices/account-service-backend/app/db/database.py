import logging

from tortoise import Tortoise

from app.core.settings import get_settings

logger = logging.getLogger("db")

TORTOISE_ORM = {
    "connections": {"default": ""},
    "apps": {
        "models": {
            "models": ["app.db.models", "aerich.models"],
            "default_connection": "default",
        }
    },
}


def build_tortoise_config(database_url: str) -> dict:
    cfg = {
        "connections": {"default": database_url},
        "apps": {
            "models": {
                "models": ["app.db.models", "aerich.models"],
                "default_connection": "default",
            }
        },
    }
    return cfg


async def init_db(database_url: str | None = None) -> None:
    url = database_url or get_settings().database_url
    await Tortoise.init(config=build_tortoise_config(url))
    await Tortoise.generate_schemas(safe=True)
    logger.info("Tortoise initialised at %s", url.split("@")[-1])


async def close_db() -> None:
    await Tortoise.close_connections()
