"""lm-eval backend that keeps the effective request free of dead fields.

The local chat-completions backend of lm-eval accepts a task YAML and merges
the CLI ``--gen_kwargs`` into its ``generation_kwargs`` key by key. Two fields
from the task contract never reach the server in a usable form:

``do_sample``
    The backend pops it while building the payload, so a task YAML that sets
    ``do_sample: false`` cannot make a run deterministic. Its presence in the
    request suggests a determinism that does not exist.

``max_gen_toks``
    The backend prefers ``max_tokens`` and only falls back to ``max_gen_toks``.
    Because the project always sends ``max_tokens``, the task's own limit
    travels as a second, contradicting field.

The task YAML keeps both fields because lm-eval uses ``max_gen_toks``
internally for the context budget. This backend therefore removes them from
the request only, not from the task configuration.
"""

from __future__ import annotations

from typing import Any

from lm_eval.models.openai_completions import LocalChatCompletion

#: Fields that must not travel with the request.
DEAD_REQUEST_FIELDS = frozenset({"do_sample", "max_gen_toks"})


class BenchmarksChatCompletion(LocalChatCompletion):
    """Local chat completions without the ineffective request fields."""

    def _create_payload(
        self,
        messages: list[dict[str, Any]],
        generate: bool = False,
        gen_kwargs: dict[str, Any] | None = None,
        seed: int = 1234,
        eos: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if gen_kwargs:
            gen_kwargs = {
                key: value
                for key, value in gen_kwargs.items()
                if key not in DEAD_REQUEST_FIELDS
            }
        # The explicit form keeps the method usable with test doubles that
        # do not inherit from the backend class.
        return LocalChatCompletion._create_payload(
            self,
            messages,
            generate=generate,
            gen_kwargs=gen_kwargs,
            seed=seed,
            eos=eos,
            **kwargs,
        )


def register() -> None:
    """Register the backend under its project-specific name."""
    from lm_eval.api.registry import model_registry

    model_registry.register(
        "benchmarks-chat-completions",
        target="lmeval_backend:BenchmarksChatCompletion",
    )
