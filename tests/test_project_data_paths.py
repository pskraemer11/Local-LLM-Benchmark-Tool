"""Public entry points share the migrated data and documentation locations."""

from pathlib import Path

import assemble_blueprint
import benchmark_config
import model_registry
import registry_tool


def test_registry_entry_points_use_runtime_data_directory():
    root = Path(__file__).resolve().parents[1]
    expected = root / "data" / "model_registry.yaml"
    assert registry_tool.REGISTRY_PATH == expected
    assert assemble_blueprint.REGISTRY_PATH.resolve() == expected
    assert model_registry._DEFAULT_REGISTRY_PATH == expected


def test_template_and_blueprint_consumers_use_docs_directory():
    root = Path(__file__).resolve().parents[1]
    templates = root / "docs" / "Jinja-Chat-Templates"
    assert templates.is_dir()
    assert registry_tool.TEMPLATE_DIR == templates
    assert assemble_blueprint.TEMPLATE_DIR.resolve() == templates
    assert benchmark_config._TEMPLATE_ROOT == templates
    assert model_registry._DEFAULT_TEMPLATE_ROOT == templates
    assert assemble_blueprint.BLUEPRINT_PATH.resolve() == root / "docs" / "blueprint_definitions.yaml"
    assert assemble_blueprint.BLUEPRINT_PATH.is_file()
