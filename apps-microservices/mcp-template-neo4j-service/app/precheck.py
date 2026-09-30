"""One-shot Neo4j connectivity check, run before an admin-requested spawn.

Only the admin API (create / rotate) calls this: the boot and periodic
reconcile paths spawn without it, so a Neo4j blip while the runner restarts
never orphans instances (mcp-neo4j-cypher reconnects on its own).
"""
from __future__ import annotations

import asyncio

from neo4j import AsyncGraphDatabase
from neo4j.exceptions import (
    AuthError,
    ClientError,
    ConfigurationError,
    DriverError,
    Neo4jError,
    ServiceUnavailable,
)

from app.neo4j_env import Neo4jCredentials

_DATABASE_NOT_FOUND = "Neo.ClientError.Database.DatabaseNotFound"


class PrecheckError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


async def _ping(driver, database: str) -> None:
    async with driver.session(database=database) as session:
        result = await session.run("RETURN 1")
        await result.consume()


async def verify_connection(creds: Neo4jCredentials, timeout: float) -> None:
    """Raise PrecheckError unless the credentials open a session on the
    configured database. Error messages never include the password."""
    try:
        driver = AsyncGraphDatabase.driver(
            creds.uri,
            auth=(creds.username, creds.password),
            connection_timeout=timeout,
        )
    except (ConfigurationError, ValueError) as e:
        raise PrecheckError("neo4j_invalid_uri", f"invalid Neo4j URI {creds.uri!r}") from e
    try:
        await asyncio.wait_for(_ping(driver, creds.database), timeout=timeout)
    except AuthError as e:  # subclass of ClientError: must come first
        raise PrecheckError("neo4j_auth_failed", "Neo4j rejected the username or password") from e
    except ClientError as e:
        if e.code == _DATABASE_NOT_FOUND:
            raise PrecheckError(
                "neo4j_database_not_found", f"database {creds.database!r} does not exist"
            ) from e
        raise PrecheckError("neo4j_error", f"Neo4j refused the connection check ({e.code})") from e
    except (ServiceUnavailable, OSError, asyncio.TimeoutError) as e:
        raise PrecheckError("neo4j_unreachable", f"Neo4j unreachable at {creds.uri}") from e
    except (Neo4jError, DriverError) as e:
        raise PrecheckError("neo4j_error", f"Neo4j connection check failed ({type(e).__name__})") from e
    finally:
        await driver.close()
