import pytest
from pathlib import Path

from app.credentials import CredentialsStore


@pytest.fixture
def tmp_store(tmp_path):
    return CredentialsStore(base_dir=str(tmp_path))


def test_write_creates_dir_with_credential_file(tmp_store):
    dir_path = tmp_store.write("abc", "{\"x\":1}")
    # The returned path is a directory.
    assert Path(dir_path).is_dir()
    assert oct(Path(dir_path).stat().st_mode)[-3:] == "700"
    # service_account_credentials.json lives inside at mode 0600.
    file_path = Path(dir_path) / CredentialsStore.CRED_FILENAME
    assert file_path.is_file()
    assert oct(file_path.stat().st_mode)[-3:] == "600"
    assert file_path.read_text() == "{\"x\":1}"


def test_shred_removes_dir(tmp_store):
    dir_path = tmp_store.write("abc", "{}")
    tmp_store.shred("abc")
    assert not Path(dir_path).exists()


def test_shred_missing_is_noop(tmp_store):
    tmp_store.shred("never-existed")


def test_path_for_returns_dir(tmp_store):
    dir_path = tmp_store.write("abc", "{}")
    assert dir_path == tmp_store.path_for("abc")


def test_credential_file_for_points_inside_dir(tmp_store):
    dir_path = tmp_store.write("abc", "{}")
    expected = str(Path(dir_path) / CredentialsStore.CRED_FILENAME)
    assert tmp_store.credential_file_for("abc") == expected


@pytest.mark.parametrize(
    "bad_id",
    ["../etc/passwd", "a/b", "a\\b", ".hidden", "..", ".", "ab\x00cd", "a%2fb", ""],
)
def test_rejects_traversal_instance_id(tmp_store, bad_id):
    with pytest.raises(ValueError):
        tmp_store.path_for(bad_id)
