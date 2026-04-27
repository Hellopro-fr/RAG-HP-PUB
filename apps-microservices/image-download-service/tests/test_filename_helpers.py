from core.downloader import _url_hash8, _build_filename


def test_url_hash8_stable():
    url = "https://fournisseur.com/images/chaise-bleue.jpg"
    assert _url_hash8(url) == _url_hash8(url)


def test_url_hash8_is_8_hex_chars():
    h = _url_hash8("https://example.com/a.jpg")
    assert len(h) == 8
    assert all(c in "0123456789abcdef" for c in h)


def test_url_hash8_different_urls_differ():
    h1 = _url_hash8("https://example.com/a.jpg")
    h2 = _url_hash8("https://example.com/b.jpg")
    assert h1 != h2


def test_build_filename_format():
    result = _build_filename("chaise-bleue", "60001", "https://example.com/a.jpg", ".jpg")
    prefix = "chaise-bleue-60001-"
    assert result.startswith(prefix)
    assert result.endswith(".jpg")
    hash_part = result[len(prefix):-len(".jpg")]
    assert len(hash_part) == 8
