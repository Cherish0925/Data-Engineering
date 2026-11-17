"""Measure composition separately from source preparation, in fresh processes.

    python examples/measure_composition.py --output runs/composition-scale --records 10000 100000

The generated documents exercise I/O and sampling; they are not model-training data.
Peak RSS is reported on platforms exposing the standard-library resource module.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


def prepare(root: Path, count: int, payload_bytes: int):
    from ai_data import build
    from ai_data.contracts import dumps

    root.mkdir(parents=True, exist_ok=False)
    with (root / "records.jsonl").open("w", encoding="utf-8") as stream:
        for index in range(count):
            record = {"schema_version": "1.0", "id": f"record:{index}", "kind": "document",
                      "payload": {"text": f"Generated I/O fixture {index}: " + "x" * payload_bytes},
                      "source": {"uri": "example://composition-scale", "revision": "1"},
                      "split_group": f"record:{index}", "allowed_uses": ["train"], "split": "train"}
            stream.write(dumps(record) + "\n")
    recipe = {"schema_version": "1.0", "name": "scale-source", "sources": [{"connector": "jsonl", "path": "records.jsonl"}],
              "use": "train", "seed": "scale-source", "splits": {"train": 1, "validation": 0, "test": 0}}
    (root / "source.recipe.json").write_text(dumps(recipe), encoding="utf-8")
    source = build(root / "source.recipe.json", root / "source")
    mixture = {"schema_version": "1.0", "name": "scale-mixture", "sources": [
        {"name": "documents", "path": "source", "release_id": source["release_id"], "split": "train", "weight": 1}],
        "seed": "scale-mixture", "budget": {"unit": "records", "value": count},
        "shard_records": 4096, "exhaustion": "renormalize"}
    (root / "mixture.recipe.json").write_text(dumps(mixture), encoding="utf-8")


def measure(root: Path):
    from ai_data.composition import MixtureReader, compose, verify_mixture

    started = time.perf_counter()
    manifest = compose(root / "mixture.recipe.json", root / "mixture")
    compose_seconds = time.perf_counter() - started
    try:
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_mib = rss / (1024 * 1024 if sys.platform == "darwin" else 1024)
    except ImportError:
        peak_mib = None
    verification = verify_mixture(root / "mixture")
    started = time.perf_counter()
    counts = []
    for rank in range(4):
        with MixtureReader(root / "mixture", rank=rank, world_size=4) as reader:
            counts.append(sum(1 for _ in reader))
    print(json.dumps({"input_records": manifest["sources"][0]["records"],
                      "input_bytes": manifest["sources"][0]["bytes"], "output_records": manifest["counts"]["records"],
                      "output_bytes": sum(s["bytes"] + s["index_bytes"] for s in manifest["shards"]),
                      "shards": len(manifest["shards"]), "compose_seconds": round(compose_seconds, 3),
                      "compose_peak_rss_mib": round(peak_mib, 3) if peak_mib else None,
                      "four_rank_read_seconds": round(time.perf_counter() - started, 3),
                      "rank_counts": counts, "verified": verification["ok"]}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--records", type=int, nargs="+", default=[10000, 100000])
    parser.add_argument("--payload-bytes", type=int, default=512)
    parser.add_argument("--phase", choices=("prepare", "measure"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = args.output.resolve()
    if args.phase == "prepare":
        prepare(root, args.records[0], args.payload_bytes)
    elif args.phase == "measure":
        measure(root)
    else:
        root.mkdir(parents=True, exist_ok=False)
        results = []
        for count in args.records:
            case = root / str(count)
            command = [sys.executable, str(Path(__file__).resolve()), "--output", str(case), "--records", str(count),
                       "--payload-bytes", str(args.payload_bytes)]
            subprocess.run([*command, "--phase", "prepare"], check=True)
            result = subprocess.run([*command, "--phase", "measure"], check=True, capture_output=True, text=True)
            value = json.loads(result.stdout)
            results.append(value)
            print(json.dumps(value), flush=True)
        (root / "measurements.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
