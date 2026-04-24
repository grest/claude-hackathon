"""Central registry — maps (metric_name, version) -> definition module."""

from definitions.metrics_v1 import ALL_METRICS as V1_METRICS, ChurnMetricDefinition

_REGISTRY: dict[tuple[str, str], ChurnMetricDefinition] = {
    (name, "v1"): defn for name, defn in V1_METRICS.items()
}


def get_definition(metric_name: str, version: str = "v1") -> ChurnMetricDefinition:
    key = (metric_name, version)
    if key not in _REGISTRY:
        raise KeyError(f"No metric definition for {metric_name!r} at version {version!r}")
    return _REGISTRY[key]


def list_metrics(version: str | None = None) -> list[ChurnMetricDefinition]:
    return [
        defn
        for (name, ver), defn in _REGISTRY.items()
        if version is None or ver == version
    ]
