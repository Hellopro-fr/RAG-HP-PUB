"""Neo4j credentials parsing and child-process environment for one instance.

The gateway sends the decrypted credentials as a JSON string
({"uri","username","password","database"}). Nothing is written to disk:
the values go straight into the mcp-neo4j-cypher subprocess environment.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field

DEFAULT_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# mcp-neo4j-cypher reads NEO4J_URL *before* NEO4J_URI, and NEO4J_TRANSPORT /
# NEO4J_MCP_SERVER_* would switch it off stdio (mcp-proxy needs stdio). The
# connection variables are owned by the runner, never by the template env.
_RESERVED_KEYS = frozenset(
    {
        "NEO4J_URL",
        "NEO4J_URI",
        "NEO4J_USERNAME",
        "NEO4J_PASSWORD",
        "NEO4J_DATABASE",
        "NEO4J_TRANSPORT",
    }
)
_RESERVED_PREFIXES = ("NEO4J_MCP_SERVER_",)


class InvalidCredentials(ValueError):
    """credentials_json does not describe a usable Neo4j connection."""


@dataclass(frozen=True)
class Neo4jCredentials:
    uri: str
    username: str
    password: str = field(repr=False)
    database: str = "neo4j"


def parse_credentials(raw: str) -> Neo4jCredentials:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        raise InvalidCredentials("credentials_json is not valid JSON") from e
    if not isinstance(data, dict):
        raise InvalidCredentials("credentials_json must be a JSON object")
    values: dict[str, str] = {}
    for key in ("uri", "username", "password"):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise InvalidCredentials(f"credentials_json.{key} is required")
        values[key] = value
    database = data.get("database") or "neo4j"
    if not isinstance(database, str):
        raise InvalidCredentials("credentials_json.database must be a string")
    return Neo4jCredentials(
        uri=values["uri"].strip(),
        username=values["username"],
        password=values["password"],
        database=database.strip() or "neo4j",
    )


def _is_reserved(key: str) -> bool:
    return key in _RESERVED_KEYS or key.startswith(_RESERVED_PREFIXES)


# mcp-neo4j-cypher CLI flags win over env vars, so the template's stdio_args
# must not carry any connection/transport flag either ("--password" on argv
# would also be visible in `ps`). Its parser is a plain argparse.ArgumentParser
# (allow_abbrev=True): "--pass" IS "--password", so any long option that is a
# prefix of a reserved flag is rejected too.
_RESERVED_FLAGS = (
    "--db-url",
    "--username",
    "--password",
    "--database",
    "--transport",
    "--server-path",
    "--server-host",
    "--server-port",
    "--allow-origins",
    "--allowed-hosts",
)


def check_stdio_args(args: list[str]) -> None:
    for arg in args:
        name = arg.split("=", 1)[0]
        if len(name) > 2 and name.startswith("--") and any(f.startswith(name) for f in _RESERVED_FLAGS):
            raise InvalidCredentials(f"stdio_args may not set {name}: the runner owns the connection")


def build_process_env(
    base: Mapping[str, str],
    template_env: Mapping[str, str],
    creds: Neo4jCredentials,
) -> dict[str, str]:
    """Minimal child env: PATH/HOME/LANG from the runner (execvp needs PATH),
    then the template env minus reserved keys, then the connection variables
    last so nothing upstream can override them. The runner's own secrets
    (RUNNER_ADMIN_TOKEN, ...) are never inherited."""
    env = {
        "PATH": base.get("PATH", DEFAULT_PATH),
        "HOME": base.get("HOME", "/tmp"),
        "LANG": base.get("LANG", "C.UTF-8"),
    }
    env.update({k: v for k, v in template_env.items() if not _is_reserved(k)})
    env.update(
        {
            "NEO4J_URI": creds.uri,
            "NEO4J_USERNAME": creds.username,
            "NEO4J_PASSWORD": creds.password,
            "NEO4J_DATABASE": creds.database,
        }
    )
    return env
