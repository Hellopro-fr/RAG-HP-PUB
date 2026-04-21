import pytest
from pathlib import Path

from app.credentials import CredentialsStore


@pytest.fixture
def tmp_store(tmp_path):
    return CredentialsStore(base_dir=str(tmp_path))


def test_write_creates_file_mode_600(tmp_store):
    p = tmp_store.write("abc", "{\"x\":1}")
    assert Path(p).is_file()
    assert oct(Path(p).stat().st_mode)[-3:] == "600"


def test_shred_removes_file(tmp_store):
    p = tmp_store.write("abc", "{}")
    tmp_store.shred("abc")
    assert not Path(p).exists()


def test_shred_missing_is_noop(tmp_store):
    tmp_store.shred("never-existed")


def test_path_is_predictable(tmp_store):
    p1 = tmp_store.write("abc", "{}")
    p2 = tmp_store.path_for("abc")
    assert p1 == p2


@pytest.mark.parametrize(
    "bad_id",
    ["../etc/passwd", "a/b", "a\\b", ".hidden", "..", "."],
)
def test_rejects_traversal_instance_id(tmp_store, bad_id):
    with pytest.raises(ValueError):
        tmp_store.path_for(bad_id)
