import pytest

from app.neo4j_env import (
    InvalidCredentials,
    Neo4jCredentials,
    build_process_env,
    check_stdio_args,
    parse_credentials,
)

VALID = '{"uri":"bolt://neo4j:7687","username":"reader","password":"s3cret","database":"graph"}'


def test_parse_valid():
    assert parse_credentials(VALID) == Neo4jCredentials(
        uri="bolt://neo4j:7687", username="reader", password="s3cret", database="graph"
    )


def test_parse_defaults_database():
    creds = parse_credentials('{"uri":"bolt://h:7687","username":"u","password":"p"}')
    assert creds.database == "neo4j"


def test_parse_blank_database_defaults():
    creds = parse_credentials('{"uri":"bolt://h:7687","username":"u","password":"p","database":"  "}')
    assert creds.database == "neo4j"


@pytest.mark.parametrize(
    "raw,msg",
    [
        ("not json", "not valid JSON"),
        ("[]", "JSON object"),
        ('{"username":"u","password":"p"}', "uri"),
        ('{"uri":"bolt://h","password":"p"}', "username"),
        ('{"uri":"bolt://h","username":"u","password":"  "}', "password"),
        ('{"uri":"bolt://h","username":"u","password":"p","database":5}', "database"),
    ],
)
def test_parse_rejects(raw, msg):
    with pytest.raises(InvalidCredentials, match=msg):
        parse_credentials(raw)


def test_repr_hides_password():
    assert "s3cret" not in repr(parse_credentials(VALID))


def test_env_credentials_and_read_only():
    env = build_process_env(
        {"PATH": "/bin", "HOME": "/home/runner", "LANG": "C.UTF-8", "RUNNER_ADMIN_TOKEN": "leak"},
        {"NEO4J_READ_ONLY": "true"},
        parse_credentials(VALID),
    )
    assert env == {
        "PATH": "/bin",
        "HOME": "/home/runner",
        "LANG": "C.UTF-8",
        "NEO4J_READ_ONLY": "true",
        "NEO4J_URI": "bolt://neo4j:7687",
        "NEO4J_USERNAME": "reader",
        "NEO4J_PASSWORD": "s3cret",
        "NEO4J_DATABASE": "graph",
    }


def test_env_template_cannot_override_connection():
    env = build_process_env(
        {},
        {
            "NEO4J_URL": "bolt://evil:7687",
            "NEO4J_URI": "bolt://evil:7687",
            "NEO4J_PASSWORD": "x",
            "NEO4J_TRANSPORT": "http",
            "NEO4J_MCP_SERVER_PORT": "9999",
            "NEO4J_READ_ONLY": "false",
        },
        parse_credentials(VALID),
    )
    assert env["NEO4J_URI"] == "bolt://neo4j:7687"
    assert env["NEO4J_PASSWORD"] == "s3cret"
    assert env["NEO4J_READ_ONLY"] == "false"
    for key in ("NEO4J_URL", "NEO4J_TRANSPORT", "NEO4J_MCP_SERVER_PORT"):
        assert key not in env
    assert env["PATH"]  # default PATH when the base env has none


@pytest.mark.parametrize(
    "args",
    [
        ["--db-url", "bolt://evil:7687"],
        ["--password=x"],
        ["--username", "admin"],
        ["--database", "other"],
        ["--transport", "http"],
        ["--server-port", "9999"],
        ["--allow-origins", "*"],
        ["--allowed-hosts", "*"],
        # argparse abbreviations (allow_abbrev=True upstream)
        ["--db", "bolt://evil:7687"],
        ["--pass", "x"],
        ["--user", "admin"],
        ["--data", "other"],
        ["--trans", "http"],
        ["--serv", "9999"],
    ],
)
def test_stdio_args_cannot_override_connection(args):
    # mcp-neo4j-cypher reads CLI flags BEFORE env vars (utils.process_config).
    with pytest.raises(InvalidCredentials, match="stdio_args may not set"):
        check_stdio_args(args)


def test_stdio_args_other_flags_allowed():
    check_stdio_args([])
    check_stdio_args(["--read-timeout", "30"])
