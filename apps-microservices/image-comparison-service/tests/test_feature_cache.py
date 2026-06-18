"""Unit tests for feature_cache serialization. Run on the VM (needs cv2/imagehash/numpy/PIL):
    cd apps-microservices/image-comparison-service && python -m pytest tests/test_feature_cache.py -v
No Redis required — these cover the pure serialize/deserialize seam."""
import numpy as np
import cv2
import imagehash
from PIL import Image

from app.core.feature_cache import serialize_feature, deserialize_feature, feature_key
from app.core.image_processor import ImageProcessor


def _make_feature(seed: int):
    rng = np.random.default_rng(seed)
    arr = (rng.random((64, 64, 3)) * 255).astype("uint8")
    return ImageProcessor.extract_features(Image.fromarray(arr, "RGB"))


def test_round_trip_preserves_hamming_and_correlation():
    f1 = _make_feature(1)
    f2 = _make_feature(2)
    r1 = deserialize_feature(serialize_feature(f1))
    r2 = deserialize_feature(serialize_feature(f2))
    assert r1 is not None and r2 is not None
    # pHash Hamming distance identical after round-trip
    assert (f1["phash"] - f2["phash"]) == (r1["phash"] - r2["phash"])
    # Histogram correlation identical (rebuilt hist must be float32 + same shape)
    orig = cv2.compareHist(f1["hist"], f2["hist"], cv2.HISTCMP_CORREL)
    back = cv2.compareHist(r1["hist"], r2["hist"], cv2.HISTCMP_CORREL)
    assert abs(orig - back) < 1e-6
    assert r1["hist"].dtype == np.float32


def test_self_similarity_identical_after_round_trip():
    f1 = _make_feature(7)
    r1 = deserialize_feature(serialize_feature(f1))
    score_orig, _ = ImageProcessor.calculate_similarity(f1, f1)
    score_back, _ = ImageProcessor.calculate_similarity(r1, r1)
    assert score_orig == score_back == 100.0


def test_corrupt_payload_is_treated_as_miss():
    assert deserialize_feature("not json") is None
    assert deserialize_feature('{"phash": "zz"}') is None  # missing hist / bad hex
    assert deserialize_feature('{"hist": [1,2,3]}') is None  # missing phash


def test_feature_key_is_deterministic_and_namespaced():
    k = feature_key("https://example.com/a.jpg")
    assert k == feature_key("https://example.com/a.jpg")
    assert k.startswith("imgfeat:")
    assert feature_key("https://example.com/a.jpg") != feature_key("https://example.com/b.jpg")
