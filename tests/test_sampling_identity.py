"""Sampling evidence must prove the actual model, variant and source scope."""

import json
from pathlib import Path

import pytest

import registry_tool as rt
from inventory import IdentityLink
from model_identity import ArtifactIdentityEvidence
from sampling_research import research_sampling_report


def test_hf_search_cannot_confirm_unrelated_repository_or_its_base():
    def fetch(url, _timeout):
        if "api/models?search=" in url:
            return json.dumps([{"id": "vendor/model-other", "tags": ["base_model:quantized:other/base"]}])
        if "/raw/" in url and ("model-other" in url or "other/base" in url):
            return "Recommended: temperature=0.91, top_p=0.77"
        return None

    report = research_sampling_report({"modelKey": "vendor/model"}, fetcher=fetch)
    assert report["sampling_research_status"] != "confirmed"
    assert "coding" not in report["sampling"]


@pytest.mark.parametrize("relation", ["finetune", "merge", "adapter", None])
def test_lineage_without_explicit_quantization_cannot_supply_sampling(relation):
    def fetch(url, _timeout):
        if url == "https://huggingface.co/api/models/vendor/variant?full=false":
            return json.dumps(
                {"id": "vendor/variant", "cardData": {"base_model": "vendor/base", "base_model_relation": relation}}
            )
        if url == "https://huggingface.co/vendor/base/raw/main/README.md":
            return "Recommended: temperature=0.91, top_p=0.77"
        return None

    report = research_sampling_report({"modelKey": "vendor/variant"}, fetcher=fetch)
    assert report["sampling_research_status"] != "confirmed"


def test_quantized_chain_can_supply_the_exact_base_profile():
    def fetch(url, _timeout):
        if url == "https://huggingface.co/api/models/vendor/variant?full=false":
            return json.dumps({"id": "vendor/variant", "tags": ["base_model:quantized:publisher/exact-base"]})
        if url == "https://huggingface.co/publisher/exact-base/raw/main/README.md":
            return "Recommended: temperature=0.7, top_p=0.8"
        return None

    report = research_sampling_report({"modelKey": "vendor/variant"}, fetcher=fetch)
    assert report["sampling_research_status"] == "confirmed"
    assert report["sampling"]["coding"]["temperature"] == 0.7
    assert report["sampling_sources"] == ["https://huggingface.co/publisher/exact-base/raw/main/README.md"]


def test_explicit_url_to_another_model_is_not_identity_evidence():
    def fetch(url, _timeout):
        return "Recommended: temperature=0.91, top_p=0.77" if "/other-model/raw/" in url else None

    report = research_sampling_report(
        {"modelKey": "vendor/model", "hf_url": "https://huggingface.co/vendor/other-model"}, fetcher=fetch
    )
    assert report["sampling_research_status"] != "confirmed"


def test_official_document_link_does_not_authorize_a_different_variant():
    def fetch(url, _timeout):
        if url == "https://huggingface.co/qwen/exact-model/raw/main/README.md":
            return "See [official docs](https://qwen.readthedocs.io/en/latest/sampling.html)."
        if url == "https://qwen.readthedocs.io/en/latest/sampling.html":
            return "# qwen/other-model\nRecommended: temperature=0.91, top_p=0.77"
        return None

    report = research_sampling_report({"modelKey": "qwen/exact-model"}, fetcher=fetch)
    assert report["sampling_research_status"] != "confirmed"


def test_exact_official_section_excludes_adjacent_model_profile():
    def fetch(url, _timeout):
        if url == "https://huggingface.co/qwen/exact-model/raw/main/README.md":
            return "See [official docs](https://qwen.readthedocs.io/en/latest/sampling.html)."
        if url == "https://qwen.readthedocs.io/en/latest/sampling.html":
            return "# qwen/exact-model\nRecommended: temperature=0.7, top_p=0.8\n# qwen/other-model\nRecommended: temperature=0.91, top_p=0.77"
        return None

    report = research_sampling_report({"modelKey": "qwen/exact-model"}, fetcher=fetch)
    assert report["sampling_research_status"] == "confirmed"
    assert report["sampling"]["coding"]["temperature"] == 0.7


def test_card_section_for_another_model_cannot_supply_values():
    def fetch(url, _timeout):
        if url == "https://huggingface.co/vendor/exact-model/raw/main/README.md":
            return "# vendor/other-model\nRecommended: temperature=0.91, top_p=0.77"
        return None

    report = research_sampling_report({"modelKey": "vendor/exact-model"}, fetcher=fetch)
    assert report["sampling_research_status"] != "confirmed"


def test_plain_official_heading_for_a_finetune_is_not_the_base_model():
    def fetch(url, _timeout):
        if url == "https://huggingface.co/qwen/Qwen3.6-27B/raw/main/README.md":
            return "See [official docs](https://qwen.readthedocs.io/en/latest/sampling.html)."
        if url == "https://qwen.readthedocs.io/en/latest/sampling.html":
            return "# Qwen3.6-27B-Heretic\nRecommended: temperature=0.91, top_p=0.77"
        return None

    report = research_sampling_report({"modelKey": "qwen/Qwen3.6-27B"}, fetcher=fetch)
    assert report["sampling_research_status"] == "unresolved"


def test_missing_identitylink_cannot_be_replaced_by_guessed_registry_urls():
    def fetch(url, _timeout):
        return "Recommended: temperature=0.91, top_p=0.77" if "/raw/" in url else None

    report = research_sampling_report(
        {"modelKey": "vendor/model", "hf_url": "https://huggingface.co/vendor/model", "proven_hf_repositories": []},
        fetcher=fetch,
    )
    assert report["sampling_research_status"] != "confirmed"


def test_registry_research_input_uses_the_exact_identitylink_package(tmp_path):
    key = "vendor/model@q6_k"
    path = tmp_path / "vendor" / "Model-GGUF" / "Model-Q6_K.gguf"
    link = IdentityLink(key, artifact_evidence=(ArtifactIdentityEvidence.from_reference(path, "vendor/Model-GGUF", "q6_k"),))
    inventory = rt.RegistryInventory({key: {}}, [], [], [], [], identity_links={key: link})

    model = rt._sampling_research_model(key, {"hf_url": "https://huggingface.co/other/unrelated"}, inventory)

    assert model["proven_hf_repositories"] == ["vendor/Model-GGUF"]


def test_registry_research_without_artifact_identity_fails_closed():
    key = "vendor/model@q6_k"
    inventory = rt.RegistryInventory({key: {}}, [], [], [], [])
    assert (
        rt._sampling_research_model(key, {"hf_url": "https://huggingface.co/vendor/model"}, inventory)[
            "proven_hf_repositories"
        ]
        == []
    )


def test_dedicated_card_plain_sibling_heading_cannot_supply_profile():
    def fetch(url, _timeout):
        if url == "https://huggingface.co/qwen/Qwen3.6-27B/raw/main/README.md":
            return "# Qwen3.6-27B-Heretic\nRecommended: temperature=0.91, top_p=0.77"
        return None

    report = research_sampling_report({"modelKey": "qwen/Qwen3.6-27B"}, fetcher=fetch)
    assert report["sampling_research_status"] != "confirmed"


@pytest.mark.parametrize("heading", ["qwen/Qwen3.6-27B-Heretic", "Qwen3.6-27B-Heretic"])
def test_exact_parent_heading_does_not_authorize_a_sibling_subsection(heading):
    def fetch(url, _timeout):
        if url == "https://huggingface.co/qwen/Qwen3.6-27B/raw/main/README.md":
            return f"# qwen/Qwen3.6-27B\n## {heading}\nRecommended: temperature=0.91, top_p=0.77"
        return None

    report = research_sampling_report({"modelKey": "qwen/Qwen3.6-27B"}, fetcher=fetch)
    assert report["sampling_research_status"] != "confirmed"


def test_registry_web_roots_preserve_huggingface_cache_repository(tmp_path):
    key = "vendor/model@q6_k"
    path = tmp_path / "hub/models--vendor--Model-GGUF/snapshots/revision/Model-Q6_K.gguf"
    evidence = ArtifactIdentityEvidence.from_reference(path, "vendor/Model-GGUF", "q6_k")
    inventory = rt.RegistryInventory({key: {}}, [], [], [], [], identity_links={key: IdentityLink(key, artifact_evidence=(evidence,))})
    assert rt._sampling_research_model(key, {}, inventory)["proven_hf_repositories"] == ["vendor/Model-GGUF"]


@pytest.mark.parametrize("reference,quant", [("foreign/Model-GGUF", "q6_k"), ("vendor/Model-GGUF", "q4_k_m")])
def test_registry_web_roots_reject_conflicting_artifact_evidence(tmp_path, reference, quant):
    key = "vendor/model@q6_k"
    path = tmp_path / "vendor/Model-GGUF/Model-Q6_K.gguf"
    evidence = ArtifactIdentityEvidence.from_reference(path, reference, quant)
    inventory = rt.RegistryInventory({key: {}}, [], [], [], [], identity_links={key: IdentityLink(key, artifact_evidence=(evidence,))})
    assert rt._sampling_research_model(key, {}, inventory)["proven_hf_repositories"] == []
