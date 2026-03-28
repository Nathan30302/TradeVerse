"""Prometheus metrics for TradeVerse imports and jobs."""
try:
    from prometheus_client import Counter, Histogram
    _HAS_PROM = True
except Exception:
    _HAS_PROM = False

# Provide labeled metrics for more detailed monitoring: labels: broker, job_type
if _HAS_PROM:
    imports_jobs_saved_total = Counter(
        'tradeverse_imports_jobs_saved_total',
        'Total number of trades saved from imports',
        ['broker', 'job_type']
    )

    imports_jobs_failed_total = Counter(
        'tradeverse_imports_jobs_failed_total',
        'Total number of failed import jobs',
        ['broker', 'job_type']
    )

    imports_job_duration_seconds = Histogram(
        'tradeverse_imports_job_duration_seconds',
        'Duration of import jobs in seconds',
        ['broker', 'job_type']
    )
else:
    # Dummy no-op metrics
    class _NoopMetric:
        def labels(self, *args, **kwargs):
            return self
        def inc(self, *a, **k):
            pass
        def observe(self, *a, **k):
            pass

    imports_jobs_saved_total = _NoopMetric()
    imports_jobs_failed_total = _NoopMetric()
    imports_job_duration_seconds = _NoopMetric()


def _normalize_label(v):
    return str(v) if v is not None else 'unknown'


def record_job_saved(count=1, broker=None, job_type=None):
    try:
        b = _normalize_label(broker)
        jt = _normalize_label(job_type)
        imports_jobs_saved_total.labels(b, jt).inc(count)
    except Exception:
        pass


def record_job_failed(count=1, broker=None, job_type=None):
    try:
        b = _normalize_label(broker)
        jt = _normalize_label(job_type)
        imports_jobs_failed_total.labels(b, jt).inc(count)
    except Exception:
        pass


def observe_job_duration(seconds, broker=None, job_type=None):
    try:
        b = _normalize_label(broker)
        jt = _normalize_label(job_type)
        imports_job_duration_seconds.labels(b, jt).observe(seconds)
    except Exception:
        pass
