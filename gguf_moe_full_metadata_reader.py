### Lesen von Header und Metadaten von GGUF-Dateien ###

import argparse
import json
import re
from pathlib import Path
from typing import Any, Optional
from gguf import GGUFReader


def _read_metadata(reader: GGUFReader) -> dict[str, Any]:
    """Liest alle Metadaten aus reader.fields (gguf 0.19.0 API)."""
    result = {}
    skip_keys = {"tokenizer.ggml.tokens", "tokenizer.ggml.token_type", "tokenizer.ggml.merges"}
    for key, field in reader.fields.items():
        if key.startswith("GGUF.") or key in skip_keys:
            continue
        try:
            result[key] = field.contents()
        except Exception:
            result[key] = str(field)
    return result


def _tensor_info(tensor: Any) -> dict[str, Any]:
    """Baut ein serialisierbares Dict aus einem ReaderTensor (gguf 0.19.0)."""
    return {
        "name": tensor.name,
        "shape": tensor.shape.tolist(),
        "tensor_type": tensor.tensor_type.name,
        "n_elements": int(tensor.n_elements),
        "n_bytes": int(tensor.n_bytes),
        "data_offset": int(tensor.data_offset),
    }


def extract_all_moe_metadata(file_path: str, output_json: Optional[str] = None) -> Optional[dict]:
    """Extrahiert alle Metadaten aus einer GGUF-Datei fuer gguf 0.19.0."""
    try:
        path = Path(file_path)
        if not path.exists():
            print(f"Fehler: Datei nicht gefunden: {file_path}")
            return None

        reader = GGUFReader(file_path)
        metadata: dict[str, Any] = {"general": {}, "moe": {}, "tensors": []}

        metadata["general"] = _read_metadata(reader)

        moe_keys = [k for k in metadata["general"] if re.search(r"(?i)(moe|expert|router)", k)]
        for key in moe_keys:
            metadata["moe"][key] = metadata["general"][key]

        experts: dict[str, Any] = {}
        router_tensors: list[dict[str, Any]] = []

        for tensor in reader.tensors:
            info = _tensor_info(tensor)

            if "expert" in tensor.name.lower():
                info["is_expert"] = True
                parts = tensor.name.split(".")
                expert_id = next((p for p in parts if p.isdigit()), tensor.name)
                expert_layer = parts[-1] if len(parts) > 1 else "unknown"

                if expert_id not in experts:
                    experts[expert_id] = {"id": expert_id, "layers": {}}
                experts[expert_id]["layers"][expert_layer] = info

            elif "router" in tensor.name.lower():
                info["is_router"] = True
                router_tensors.append(info)

            else:
                info["is_expert"] = False
                metadata["tensors"].append(info)

        if experts:
            metadata["moe"]["experts"] = list(experts.values())
        if router_tensors:
            metadata["moe"]["router_tensors"] = router_tensors

        print("\n=== GGUF-Metadaten (vollstaendig, inkl. MoE) ===")
        print(json.dumps(metadata, indent=4, ensure_ascii=False, default=str))

        if output_json:
            output_path = Path(output_json)
            output_path.write_text(
                json.dumps(metadata, indent=4, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            print(f"\nMetadaten wurden in '{output_path}' gespeichert.")

        return metadata

    except FileNotFoundError:
        print(f"Fehler: Datei nicht gefunden: {file_path}")
    except Exception as e:
        print(f"Fehler beim Auslesen der GGUF-Datei: {e}")
    return None


def main():
    parser = argparse.ArgumentParser(
        description="""
Extrahiert alle Metadaten aus einer GGUF-Datei (gguf 0.19.0).

Beispiele:
  python gguf_moe_full_metadata_reader.py modell.gguf
  python gguf_moe_full_metadata_reader.py modell.gguf --output metadaten.json
        """,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("file_path", help="Pfad zur GGUF-Datei")
    parser.add_argument("--output", help="Pfad zur JSON-Ausgabedatei (optional)", default=None)

    args = parser.parse_args()
    extract_all_moe_metadata(args.file_path, args.output)


if __name__ == "__main__":
    main()
