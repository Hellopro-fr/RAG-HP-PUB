"""Tests for the per-service downstream timeout map."""


class TestDownstreamTimeouts:

    def test_detection_service_has_180s_timeout(self):
        from app.core.settings import settings
        assert settings.DOWNSTREAM_TIMEOUTS_S["api-detection-langue-fr-service"] == 180.0

    def test_unmapped_services_absent_from_map(self):
        from app.core.settings import settings
        # Other services are NOT in the map (preserves existing timeout=None behavior)
        assert "embedding-service" not in settings.DOWNSTREAM_TIMEOUTS_S
        assert "llm-service" not in settings.DOWNSTREAM_TIMEOUTS_S
