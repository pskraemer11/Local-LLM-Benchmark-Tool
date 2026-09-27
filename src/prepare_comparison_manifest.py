"""Create the four-pipeline Variant-B comparison manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from comparison_manifest import build_comparison_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a Variant-B four-pipeline comparison manifest")
    parser.add_argument("--sample-size", type=int, default=1)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("ergebnisse/benchmark-comparison-manifest.json"))
    args = parser.parse_args()
    manifest = build_comparison_manifest(args.project_root, sample_size=args.sample_size, seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.output} (Variant {manifest['variant']}, 4 pipelines, SampleSize={args.sample_size})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
