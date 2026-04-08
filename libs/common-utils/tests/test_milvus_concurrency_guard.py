import pytest
from common_utils.concurrency.config import GuardConfig
from common_utils.concurrency.metrics import GuardMetrics


class TestGuardConfig:
    def test_defaults(self):
        config = GuardConfig()
        assert config.global_max == 50
        assert config.write_ceiling == 30
        assert config.tier == 3
        assert config.lease_ttl == 60
        assert config.acquire_timeout == 30
        assert config.retry_interval == 0.5
        assert config.fallback_limit == 5
        assert config.correction_interval == 30

    def test_custom_values(self):
        config = GuardConfig(
            global_max=100,
            write_ceiling=60,
            tier=1,
            service_name="test-service",
            lease_ttl=120,
        )
        assert config.global_max == 100
        assert config.write_ceiling == 60
        assert config.tier == 1
        assert config.service_name == "test-service"
        assert config.lease_ttl == 120


class TestGuardMetrics:
    def test_metrics_registered(self):
        metrics = GuardMetrics()
        assert metrics.slots_active is not None
        assert metrics.slots_max is not None
        assert metrics.write_ceiling is not None
        assert metrics.acquire_duration is not None
        assert metrics.acquire_timeouts is not None
        assert metrics.lease_expirations is not None
        assert metrics.fallback_active is not None

    def test_record_acquire(self):
        metrics = GuardMetrics()
        metrics.record_acquire(tier="2", service="test-svc", duration=0.5)

    def test_record_release(self):
        metrics = GuardMetrics()
        metrics.record_release(tier="2", service="test-svc")

    def test_record_timeout(self):
        metrics = GuardMetrics()
        metrics.record_timeout(tier="2", service="test-svc")

    def test_set_config_gauges(self):
        metrics = GuardMetrics()
        metrics.set_config_gauges(global_max=50, write_ceiling=30)

    def test_set_fallback(self):
        metrics = GuardMetrics()
        metrics.set_fallback(service="test-svc", active=True)
        metrics.set_fallback(service="test-svc", active=False)

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("MILVUS_GLOBAL_MAX_CONCURRENT", "200")
        monkeypatch.setenv("MILVUS_WRITE_CEILING", "80")
        monkeypatch.setenv("MILVUS_CONCURRENCY_TIER", "2")
        config = GuardConfig()
        assert config.global_max == 200
        assert config.write_ceiling == 80
        assert config.tier == 2
