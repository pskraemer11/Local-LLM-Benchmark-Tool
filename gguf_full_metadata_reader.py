### Lesen von Header und Metadaten von GGUF-Dateien ###
# https://www.ecosia.org/ai-chat/1bbcffc904d8c7ce30bc563ca160a430e73f4654782e1cc01ec5be8cf2b4efbd?origin=search 

import argparse
import json
from pathlib import Path
from gguf import GGUFReader, GGUFValueType

def extract_all_gguf_metadata(file_path: str, output_json: str = None):
    """
    Extrahiert ALLE Metadaten aus einer GGUF-Datei, einschließlich MoE-spezifischer Informationen.

    Args:
        file_path (str): Pfad zur GGUF-Datei.
        output_json (str, optional): Pfad zur JSON-Ausgabedatei. Falls None, wird nichts gespeichert.
    """
    try:
        # GGUF-Datei öffnen
        gguf_reader = GGUFReader(file_path)

        # Metadaten extrahieren
        metadata = {
            "general": {
                "architecture": gguf_reader.metadata.get("general.architecture"),
                "quantization": gguf_reader.metadata.get("quantization"),
                "file_type": gguf_reader.metadata.get("general.file_type"),
                "version": gguf_reader.metadata.get("general.version"),
                "name": gguf_reader.metadata.get("general.name"),
                "author": gguf_reader.metadata.get("general.author"),
                "license": gguf_reader.metadata.get("general.license"),
            },
            "moe": {},  # MoE-spezifische Metadaten
            "tensors": [],
        }

        # MoE-spezifische Metadaten extrahieren (falls vorhanden)
        if gguf_reader.metadata.get("moe.num_experts"):
            metadata["moe"]["num_experts"] = gguf_reader.metadata.get("moe.num_experts")
            metadata["moe"]["top_k"] = gguf_reader.metadata.get("moe.top_k")
            metadata["moe"]["num_experts_per_token"] = gguf_reader.metadata.get("moe.num_experts_per_token")
            metadata["moe"]["router_aux_loss_coef"] = gguf_reader.metadata.get("moe.router_aux_loss_coef")

        # Alle Tensoren extrahieren
        for tensor in gguf_reader.tensors:
            tensor_info = {
                "name": tensor.name,
                "shape": tensor.shape,
                "type": tensor.type,
                "offset": tensor.offset,
                "n_elements": tensor.n_elements,
                "gguf_type": tensor.gguf_type,
            }

            # MoE-spezifische Tensoren identifizieren
            if "expert" in tensor.name:
                tensor_info["is_expert"] = True
                tensor_info["expert_id"] = tensor.name.split(".")[-1]  # z. B. "expert.0.weight" -> "0"
            else:
                tensor_info["is_expert"] = False

            metadata["tensors"].append(tensor_info)

        # Metadaten auf dem Terminal ausgeben
        print("\n=== GGUF-Metadaten (vollständig) ===")
        print(json.dumps(metadata, indent=4, ensure_ascii=False))

        # Optional in eine JSON-Datei schreiben
        if output_json:
            with open(output_json, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=4, ensure_ascii=False)
            print(f"\nMetadaten wurden in '{output_json}' gespeichert.")

    except Exception as e:
        print(f"Fehler beim Auslesen der GGUF-Datei: {e}")

if __name__ == "__main__":
    # Argument-Parser für die Kommandozeile
    parser = argparse.ArgumentParser(description="Extrahiert ALLE Metadaten aus einer GGUF-Datei, einschließlich MoE-spezifischer Informationen.")
    parser.add_argument("file_path", type=str, help="Pfad zur GGUF-Datei")
    parser.add_argument("--output", type=str, help="Pfad zur JSON-Ausgabedatei (optional)", default=None)

    args = parser.parse_args()

    # Skript ausführen
    extract_all_gguf_metadata(args.file_path, args.output)
