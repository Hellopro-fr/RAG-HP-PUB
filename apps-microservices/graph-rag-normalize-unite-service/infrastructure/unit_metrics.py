from prometheus_client import Counter, Gauge, Histogram

APPLIED_VERSION = Gauge("unit_registry_applied_version", "registry_version applied by this replica")
EVENTS = Counter("unit_registry_events_total", "Unit events received", ["result"])
SOURCE = Gauge("unit_registry_source", "1 for the unit-table source in use", ["source"])
BUILD_SECONDS = Histogram("unit_registry_build_seconds", "Time to build a RegistryBundle")
BUILD_FAILURES = Counter("unit_registry_build_failures_total", "RegistryBundle builds that failed")
RESYNCS = Counter("unit_registry_resync_total", "Full unit reloads from unit-registry-service")


def set_source(source: str) -> None:
    for name in ("db", "fallback"):
        SOURCE.labels(name).set(1 if name == source else 0)
