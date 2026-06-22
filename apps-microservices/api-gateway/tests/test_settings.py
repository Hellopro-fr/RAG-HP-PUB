from app.core.settings import Configuration


def test_extractor_downstream_timeout_present():
    cfg = Configuration()
    assert cfg.DOWNSTREAM_TIMEOUTS_S.get("extractor-service") == 60.0


def test_detection_timeout_unchanged():
    cfg = Configuration()
    assert cfg.DOWNSTREAM_TIMEOUTS_S.get("api-detection-langue-fr-service") == 180.0
