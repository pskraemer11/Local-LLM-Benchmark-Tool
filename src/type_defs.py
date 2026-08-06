from dataclasses import dataclass
from typing import Any, NotRequired, TypedDict


class ModelConfig(TypedDict):
    temperature: float
    top_p: float
    max_tokens: int
    enable_thinking: bool
    top_k: NotRequired[int]
    min_p: NotRequired[float | None]
    stop: NotRequired[list[str]]
    reasoning_effort: NotRequired[str]
    no_system_msg: NotRequired[bool]
    _source: NotRequired[str]


class AvailableModelInfo(TypedDict):
    key: str
    model_identifier: str
    display: str
    variant: str
    quant: str
    variants: list[Any]
    identifier: str
    params: str
    publisher: str
    _api_model: NotRequired[str | None]


class LoadedModelInfo(TypedDict):
    identifier: str
    model_identifier: str
    display_name: str
    status: str
    context_length: Any


class BenchmarkDef(TypedDict):
    key: str
    name: str
    category: str
    file: NotRequired[str]
    dataset: NotRequired[str]
    task: NotRequired[str]
    min_limit: NotRequired[int]
    timeout_mult: NotRequired[int]
    pipeline: NotRequired[str]


class TaskResult(TypedDict):
    response: str | None
    extracted_code: str
    output_status: NotRequired[str]
    entry_point_found: NotRequired[bool | None]
    score: float
    score_detail: str
    latency: float
    tokens_in: int
    tokens_out: int
    tokens_per_sec: float
    thinking_tokens: int
    truncated: NotRequired[bool]
    error_type: NotRequired[str | None]
    error_detail: NotRequired[str | None]


class PipelineResult(TypedDict):
    pipeline: str
    bench: str
    category: str
    model: str
    score: float | None
    thinking: bool
    samples: NotRequired[str]


class SandboxResult(TypedDict):
    ok: bool
    error: str | None
    state: NotRequired[dict[str, str] | None]
    passed: int
    total: int
    details: NotRequired[list[dict[str, Any]]]


class RegistryEntry(TypedDict):
    publisher: str
    hf_url: str
    arch: str
    k_cache: str
    v_cache: str
    offload: int | float
    num_parallel: int
    notes: str
    file_size_bytes: NotRequired[int]
    context_length: NotRequired[int]
    n_layers: NotRequired[int]
    hidden_dim: NotRequired[int]
    benchmark_context_limit: NotRequired[int]
    useUnifiedKvCache: NotRequired[bool]
    quants: NotRequired[list[str]]
    display_name: NotRequired[str]
    blueprint: NotRequired[str]


class SystemMetrics(TypedDict):
    cpu_percent: float
    ram_percent: float
    ram_used_gb: float
    ram_total_gb: float
    gpu_util: float | None
    gpu_mem_util: float | None
    gpu_mem_used_gb: float | None
    gpu_mem_total_gb: float | None
    gpu_temp: float | None
    vram_gb: float | None


class MetricsSummary(TypedDict):
    cpu_percent_avg: float | None
    cpu_percent_max: float | None
    gpu_util_avg: float | None
    gpu_util_max: float | None
    ram_percent_avg: float | None
    ram_percent_max: float | None
    ram_used_gb_avg: float | None
    ram_used_gb_max: float | None
    gpu_mem_used_gb_avg: float | None
    gpu_mem_used_gb_max: float | None
    gpu_temp_avg: float | None
    gpu_temp_max: float | None
    vram_gb_avg: float | None
    vram_gb_max: float | None


class PerModelBenchmarkResult(TypedDict):
    benchmark_name: str
    avg_score: float | None
    avg_latency: float | None
    avg_tps: float | None
    avg_cpu: float | None
    avg_ram: float | None
    avg_gpu: float | None
    avg_vram: float | None
    cpu_max: float | None
    gpu_max: float | None
    ram_max: float | None
    gpu_temp_max: float | None
    vram_gb: float | None


@dataclass
class GenerationConfig:
    prompt: str | None = None
    model_identifier: str | None = None
    native_model_identifier: str | None = None
    timeout: int = 120_000
    max_tokens: int = 4096
    system_msg: str | None = None
    messages: list[dict[str, Any]] | None = None
    temperature: float = 0.0
    top_p: float = 1.0
    top_k: int | None = None
    min_p: float | None = None
    is_thinking_enabled: bool | None = None
    reasoning_effort: str | None = None
    is_streaming: bool = True
    stop: list[str] | None = None
    response_format: dict | None = None
