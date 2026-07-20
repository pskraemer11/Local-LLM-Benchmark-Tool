from typing import TypedDict, Optional, NotRequired
from typing import Any


class ModelConfig(TypedDict):
    temperature: float
    top_p: float
    max_tokens: int
    enable_thinking: bool
    top_k: NotRequired[int]
    min_p: NotRequired[Optional[float]]
    stop: NotRequired[list[str]]
    reasoning_effort: NotRequired[str]
    no_system_msg: NotRequired[bool]


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
    _api_model: NotRequired[Optional[str]]


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
    response: Optional[str]
    extracted_code: str
    score: float
    score_detail: str
    latency: float
    tokens_in: int
    tokens_out: int
    tokens_per_sec: float
    thinking_tokens: int
    error_type: NotRequired[Optional[str]]
    error_detail: NotRequired[Optional[str]]


class PipelineResult(TypedDict):
    pipeline: str
    bench: str
    category: str
    model: str
    score: Optional[float]
    thinking: bool
    samples: NotRequired[str]


class SandboxResult(TypedDict):
    ok: bool
    error: Optional[str]
    state: NotRequired[Optional[dict[str, str]]]
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
    gpu_util: Optional[float]
    gpu_mem_util: Optional[float]
    gpu_mem_used_gb: Optional[float]
    gpu_mem_total_gb: Optional[float]
    gpu_temp: Optional[float]
    vram_gb: Optional[float]


class MetricsSummary(TypedDict):
    cpu_percent_avg: Optional[float]
    cpu_percent_max: Optional[float]
    gpu_util_avg: Optional[float]
    gpu_util_max: Optional[float]
    ram_percent_avg: Optional[float]
    ram_percent_max: Optional[float]
    ram_used_gb_avg: Optional[float]
    ram_used_gb_max: Optional[float]
    gpu_mem_used_gb_avg: Optional[float]
    gpu_mem_used_gb_max: Optional[float]
    gpu_temp_avg: Optional[float]
    gpu_temp_max: Optional[float]
    vram_gb_avg: Optional[float]
    vram_gb_max: Optional[float]


class PerModelBenchmarkResult(TypedDict):
    benchmark_name: str
    avg_score: Optional[float]
    avg_latency: Optional[float]
    avg_tps: Optional[float]
    avg_cpu: Optional[float]
    avg_ram: Optional[float]
    avg_gpu: Optional[float]
    avg_vram: Optional[float]
    cpu_max: Optional[float]
    gpu_max: Optional[float]
    ram_max: Optional[float]
    gpu_temp_max: Optional[float]
    vram_gb: Optional[float]
