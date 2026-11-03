"""
Prometheus metrics for Grafana (scrape /metrics with Prometheus).

- fish_speech_vram_allocated_gb / fish_speech_vram_max_gb: updated at each pipeline step
  when FISH_LOG_VRAM_STEPS=1 (and on /v1/debug/memory). Scrape interval 5–15s to see curves.
- fish_speech_tts_requests_total, fish_speech_tts_request_duration_seconds, fish_speech_tts_ttfa_seconds
- Per-function timing: prefill, decode_one_token, decode_n_tokens, forward_fast
- Per-component static weights: llm_slow, llm_fast, dac
- Per-function VRAM: delta/peak (outer) + intermediate points (inner, reported per chunk)
"""
from __future__ import annotations

from contextlib import contextmanager

try:
    from prometheus_client import REGISTRY, Counter, Gauge, Histogram, generate_latest
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    REGISTRY = None
    generate_latest = None
    _PROMETHEUS_AVAILABLE = False

GB = 1024**3

if _PROMETHEUS_AVAILABLE:
    VRAM_ALLOC_GB = Gauge(
        "fish_speech_vram_allocated_gb",
        "GPU memory allocated (GB) at last observation (pipeline step or /v1/debug/memory)",
    )
    VRAM_MAX_GB = Gauge(
        "fish_speech_vram_max_gb",
        "GPU max memory allocated (GB) since process start, at last observation",
    )
    TTS_REQUESTS_TOTAL = Counter(
        "fish_speech_tts_requests_total",
        "Total TTS requests",
        ["streaming"],
    )
    TTS_REQUEST_DURATION = Histogram(
        "fish_speech_tts_request_duration_seconds",
        "TTS request duration in seconds",
        ["streaming"],
        buckets=(0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 30.0, 60.0),
    )
    TTS_TTFA_SECONDS = Histogram(
        "fish_speech_tts_ttfa_seconds",
        "Time to first audio segment (excludes WAV header)",
        ["streaming"],
        buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
    )
    # Per-function timing
    PREFILL_SECONDS = Histogram(
        "fish_speech_prefill_seconds",
        "Prefill (first token) duration in seconds",
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0),
    )
    DECODE_ONE_TOKEN_SECONDS = Histogram(
        "fish_speech_decode_one_token_seconds",
        "Single token decode (decode_one_token_ar) duration in seconds",
        buckets=(0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2),
    )
    DECODE_N_TOKENS_SECONDS = Histogram(
        "fish_speech_decode_n_tokens_seconds",
        "Full decode_n_tokens (streaming chunk or full gen) duration in seconds",
        buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
    )
    FORWARD_FAST_SECONDS = Histogram(
        "fish_speech_forward_fast_seconds",
        "forward_generate_fast (one codebook step) duration in seconds",
        buckets=(0.0005, 0.001, 0.002, 0.005, 0.01, 0.02),
    )
    # Static model weights (GB)
    MODEL_PARAMS_GB = Gauge(
        "fish_speech_model_params_gb",
        "Model parameters memory (GB) by component",
        ["component"],
    )
    # Per-function VRAM outer (delta + peak per call)
    FUNC_VRAM_DELTA_GB = Gauge(
        "fish_speech_func_vram_delta_gb",
        "VRAM net change (GB) during last call",
        ["func"],
    )
    FUNC_VRAM_PEAK_GB = Gauge(
        "fish_speech_func_vram_peak_gb",
        "VRAM peak (GB) during last call",
        ["func"],
    )
    # Per-function VRAM inner (intermediate points, running max per chunk)
    FUNC_VRAM_INTERMEDIATE_GB = Gauge(
        "fish_speech_func_vram_intermediate_gb",
        "VRAM (GB) at intermediate point (running max over chunk)",
        ["func", "point"],
    )
else:
    VRAM_ALLOC_GB = None
    VRAM_MAX_GB = None
    TTS_REQUESTS_TOTAL = None
    TTS_REQUEST_DURATION = None
    TTS_TTFA_SECONDS = None
    PREFILL_SECONDS = None
    DECODE_ONE_TOKEN_SECONDS = None
    DECODE_N_TOKENS_SECONDS = None
    FORWARD_FAST_SECONDS = None
    MODEL_PARAMS_GB = None
    FUNC_VRAM_DELTA_GB = None
    FUNC_VRAM_PEAK_GB = None
    FUNC_VRAM_INTERMEDIATE_GB = None


def set_vram_gb(alloc_gb: float, max_gb: float) -> None:
    """Update VRAM gauges (call from inference pipeline or /v1/debug/memory)."""
    if not _PROMETHEUS_AVAILABLE or VRAM_ALLOC_GB is None or VRAM_MAX_GB is None:
        return
    VRAM_ALLOC_GB.set(alloc_gb)
    VRAM_MAX_GB.set(max_gb)


def observe_ttfa(streaming: bool, seconds: float) -> None:
    """Record time to first audio segment."""
    if not _PROMETHEUS_AVAILABLE or TTS_TTFA_SECONDS is None:
        return
    label = "true" if streaming else "false"
    TTS_TTFA_SECONDS.labels(streaming=label).observe(seconds)


def inc_tts_requests(streaming: bool, duration_seconds: float | None = None) -> None:
    """Increment TTS request counter and optionally record duration."""
    if not _PROMETHEUS_AVAILABLE:
        return
    label = "true" if streaming else "false"
    if TTS_REQUESTS_TOTAL is not None:
        TTS_REQUESTS_TOTAL.labels(streaming=label).inc()
    if duration_seconds is not None and TTS_REQUEST_DURATION is not None:
        TTS_REQUEST_DURATION.labels(streaming=label).observe(duration_seconds)


def set_model_params_gb(component: str, gb: float) -> None:
    """Report static model params size (llm_slow, llm_fast, dac)."""
    if not _PROMETHEUS_AVAILABLE or MODEL_PARAMS_GB is None:
        return
    MODEL_PARAMS_GB.labels(component=component).set(gb)


@contextmanager
def vram_track(func_label: str):
    """Context manager: measure VRAM delta + peak for a function call."""
    if not _PROMETHEUS_AVAILABLE:
        yield
        return
    try:
        import torch
        if not torch.cuda.is_available():
            yield
            return
    except Exception:
        yield
        return
    if FUNC_VRAM_DELTA_GB is None or FUNC_VRAM_PEAK_GB is None:
        yield
        return
    try:
        import torch
        torch.cuda.reset_peak_memory_stats()
        before = torch.cuda.memory_allocated()
    except Exception:
        yield
        return
    yield
    try:
        import torch
        after = torch.cuda.memory_allocated()
        peak = torch.cuda.max_memory_allocated()
        FUNC_VRAM_DELTA_GB.labels(func=func_label).set((after - before) / GB)
        FUNC_VRAM_PEAK_GB.labels(func=func_label).set(peak / GB)
    except Exception:
        pass


def set_vram_intermediate_gb(func: str, point: str, gb: float) -> None:
    """Report VRAM at intermediate point (running max over chunk)."""
    if not _PROMETHEUS_AVAILABLE or FUNC_VRAM_INTERMEDIATE_GB is None:
        return
    FUNC_VRAM_INTERMEDIATE_GB.labels(func=func, point=point).set(gb)


def get_metrics_content_type() -> str:
    return "text/plain; charset=utf-8" if _PROMETHEUS_AVAILABLE else "text/plain"


def get_metrics_body() -> bytes:
    """Prometheus exposition format for GET /metrics."""
    if _PROMETHEUS_AVAILABLE and generate_latest is not None:
        return generate_latest(REGISTRY)
    return b"# Prometheus client not installed.\n"
