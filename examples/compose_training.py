"""Create pinned source releases, compose a mixture and resume a rank reader.

Run from any directory after installation:
    python examples/compose_training.py --output runs/training-example

The authored records demonstrate data flow, not a model-quality experiment.
"""

import argparse
from pathlib import Path

from ai_data import build
from ai_data.composition import MixtureReader, compose, verify_mixture
from ai_data.contracts import dumps


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    sources = []
    for name, weight, kind, count in (("text", 3, "document", 128), ("code", 1, "document", 64)):
        path = root / name
        path.mkdir()
        with (path / "records.jsonl").open("w", encoding="utf-8") as stream:
            for index in range(count):
                text = (f"Reference document {index}: preserve the relationship between data and its source."
                        if name == "text" else f"def example_{index}(x):\n    return x + {index}\n")
                record = {"schema_version": "1.0", "id": f"{name}:{index}", "kind": kind,
                          "payload": {"text": text}, "source": {"uri": f"example://{name}", "revision": "1"},
                          "split_group": f"{name}:{index}", "split": "train", "allowed_uses": ["train", "evaluate"]}
                stream.write(dumps(record) + "\n")
        recipe = {"schema_version": "1.0", "name": name, "sources": [{"connector": "jsonl", "path": "records.jsonl"}],
                  "use": "train", "seed": "source-1", "splits": {"train": 1, "validation": 0, "test": 0}}
        (path / "recipe.json").write_text(dumps(recipe) + "\n", encoding="utf-8")
        release = build(path / "recipe.json", path / "release")
        sources.append({"name": name, "path": f"{name}/release", "release_id": release["release_id"],
                        "split": "train", "weight": weight})
    recipe = {"schema_version": "1.0", "name": "text-code-mixture", "sources": sources, "seed": "mixture-1",
              "budget": {"unit": "records", "value": 1000}, "shard_records": 128, "exhaustion": "repeat"}
    (root / "mixture.recipe.json").write_text(dumps(recipe) + "\n", encoding="utf-8")
    manifest = compose(root / "mixture.recipe.json", root / "mixture")
    with MixtureReader(root / "mixture", rank=1, world_size=4, drop_remainder=True) as reader:
        first = next(reader)
        state = reader.state_dict()
        expected_next = next(reader)["sample_index"]
    (root / "reader-state.json").write_text(dumps(state) + "\n", encoding="utf-8")
    with MixtureReader(root / "mixture", rank=1, world_size=4, drop_remainder=True) as reader:
        reader.load_state_dict(state)
        assert next(reader)["sample_index"] == expected_next
    print(dumps({"release_id": manifest["release_id"], "counts": manifest["counts"],
                 "first_rank_sample": first["sample_index"], "resumed_rank_sample": expected_next,
                 "verification": verify_mixture(root / "mixture")}))


if __name__ == "__main__":
    main()
