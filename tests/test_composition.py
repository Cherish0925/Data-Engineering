from collections import Counter, defaultdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ai_data.composition import MixtureReader, compose, verify_mixture
from ai_data.contracts import dumps
from ai_data.pipeline import build


def make_record(name, number, *, tokens=None):
    record = {"schema_version": "1.0", "id": f"{name}:{number}", "kind": "document",
              "payload": {"text": f"{name} independently authored record {number}"},
              "source": {"uri": f"example://{name}", "revision": "1"}, "split_group": f"{name}:{number}",
              "allowed_uses": ["train", "evaluate"], "split": "train"}
    if tokens is not None:
        record["metadata"] = {"token_count": tokens}
    return record


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sources = [self.source("a", 17), self.source("b", 11)]
        self.recipe = {"schema_version": "1.0", "name": "training-mixture", "sources": self.sources,
                       "seed": "split-and-sample-1", "budget": {"unit": "records", "value": 25},
                       "shard_records": 7, "exhaustion": "renormalize"}

    def source(self, name, count, *, tokens=None):
        workspace = self.root / name
        workspace.mkdir()
        rows = [make_record(name, i, tokens=tokens[i] if isinstance(tokens, list) else tokens) for i in range(count)]
        (workspace / "records.jsonl").write_text("".join(dumps(row) + "\n" for row in rows), encoding="utf-8")
        spec = {"schema_version": "1.0", "name": name,
                "sources": [{"connector": "jsonl", "path": "records.jsonl"}], "use": "train", "seed": "1",
                "splits": {"train": 1, "validation": 0, "test": 0}}
        path = workspace / "recipe.json"
        path.write_text(dumps(spec), encoding="utf-8")
        release = build(path, workspace / "release")
        return {"name": name, "path": f"{name}/release", "release_id": release["release_id"], "split": "train", "weight": 1}

    def compose(self, name="mixture"):
        path = self.root / "mix.json"
        path.write_text(dumps(self.recipe), encoding="utf-8")
        return compose(path, self.root / name)

    def read(self, name="mixture", **kwargs):
        with MixtureReader(self.root / name, **kwargs) as reader:
            return list(reader)

    def test_streamed_shards_are_reproducible_and_verified(self):
        a, b = self.compose(), self.compose("second")
        self.assertEqual(a["release_id"], b["release_id"])
        self.assertEqual([s["records"] for s in a["shards"]], [7, 7, 7, 4])
        self.assertEqual(self.read(), self.read("second"))
        self.assertTrue(verify_mixture(self.root / "mixture")["ok"])
        self.assertEqual(a["counts"]["records"], 25)
        self.assertEqual(a["stop_reason"], "budget_reached")
        self.assertFalse((self.root / "mixture/source-indexes").exists())

    def test_renormalize_exhausts_all_records_without_replacement(self):
        self.recipe["budget"]["value"] = 100
        self.recipe["sources"][0]["weight"] = 100
        result = self.compose()
        rows = self.read()
        self.assertEqual(result["stop_reason"], "all_sources_exhausted")
        self.assertEqual(len(rows), 28)
        self.assertEqual(len({row["record"]["id"] for row in rows}), 28)
        self.assertEqual(result["counts"]["source_records"], {"a": 17, "b": 11})

    def test_stop_finishes_at_first_exhausted_source(self):
        self.recipe.update(exhaustion="stop")
        self.recipe["sources"][0]["weight"] = 1000
        self.recipe["budget"]["value"] = 100
        result = self.compose()
        self.assertEqual(result["stop_reason"], "source_exhausted")
        self.assertEqual(result["counts"]["source_records"]["a"], 17)
        self.assertLess(result["counts"]["records"], 28)

    def test_repeat_weights_and_cycle_permutations(self):
        self.recipe.update(exhaustion="repeat", shard_records=128)
        self.recipe["budget"]["value"] = 1000
        self.recipe["sources"][0]["weight"] = 3
        result = self.compose()
        self.assertGreater(result["counts"]["source_records"]["a"], 700)
        self.assertLess(result["counts"]["source_records"]["a"], 800)
        by_cycle = defaultdict(list)
        for row in self.read():
            by_cycle[(row["source"]["name"], row["source"]["cycle"])].append(row["source"]["position"])
        for (name, _), positions in by_cycle.items():
            self.assertEqual(len(positions), len(set(positions)))
            self.assertLessEqual(len(positions), 17 if name == "a" else 11)
        self.assertNotEqual(by_cycle[("a", 0)], by_cycle[("a", 1)])

    def test_distributed_ownership_is_disjoint_and_complete(self):
        self.compose()
        for world_size in (1, 2, 4, 31):
            indices = []
            for rank in range(world_size):
                with MixtureReader(self.root / "mixture", rank=rank, world_size=world_size) as reader:
                    rows = list(reader)
                    self.assertEqual(len(rows), len(reader))
                    self.assertTrue(all(row["sample_index"] % world_size == rank for row in rows))
                    indices.extend(row["sample_index"] for row in rows)
            self.assertEqual(sorted(indices), list(range(25)))

    def test_checkpoint_restores_exact_next_sample(self):
        self.compose()
        expected = self.read(rank=2, world_size=4)
        with MixtureReader(self.root / "mixture", rank=2, world_size=4) as reader:
            first = [next(reader), next(reader)]
            state = json.loads(json.dumps(reader.state_dict()))
        with MixtureReader(self.root / "mixture", rank=2, world_size=4) as reader:
            reader.load_state_dict(state)
            self.assertEqual(first + list(reader), expected)
            end = reader.state_dict()
        with MixtureReader(self.root / "mixture", rank=2, world_size=4) as reader:
            reader.load_state_dict(end)
            self.assertEqual(list(reader), [])

    def test_distributed_tail_policy_equalizes_rank_lengths(self):
        self.compose()
        indices = []
        for rank in range(4):
            with MixtureReader(self.root / "mixture", rank=rank, world_size=4, drop_remainder=True) as reader:
                self.assertEqual(len(reader), 6)
                indices.extend(row["sample_index"] for row in reader)
                state = reader.state_dict()
        self.assertEqual(sorted(indices), list(range(24)))
        with MixtureReader(self.root / "mixture", rank=3, world_size=4) as reader:
            with self.assertRaisesRegex(ValueError, "worker topology"):
                reader.load_state_dict(state)

    def test_checkpoint_rejects_different_release_or_topology(self):
        self.compose()
        with MixtureReader(self.root / "mixture") as reader:
            next(reader)
            state = reader.state_dict()
        with MixtureReader(self.root / "mixture", world_size=2) as reader:
            with self.assertRaisesRegex(ValueError, "worker topology"):
                reader.load_state_dict(state)
        self.recipe["seed"] = "new-sequence"
        self.compose("second")
        with MixtureReader(self.root / "second") as reader:
            with self.assertRaisesRegex(ValueError, "different release"):
                reader.load_state_dict(state)

    def test_supplied_token_budget_stops_before_overflow(self):
        self.recipe["sources"] = [self.source("tokens", 2, tokens=[3, 4])]
        self.recipe.update(shuffle=False, exhaustion="repeat")
        self.recipe["budget"] = {"unit": "tokens", "value": 8, "token_count": "/metadata/token_count"}
        result = self.compose()
        self.assertEqual(result["counts"]["budget_units"], 7)
        self.assertEqual(result["counts"]["records"], 2)
        self.assertEqual(result["stop_reason"], "next_record_exceeds_budget")
        self.assertTrue(verify_mixture(self.root / "mixture")["ok"])

    def test_token_budget_requires_actual_supplied_counts(self):
        self.recipe["budget"] = {"unit": "tokens", "value": 10, "token_count": "/metadata/token_count"}
        with self.assertRaisesRegex(ValueError, "supplied token count"):
            self.compose()
        self.assertFalse((self.root / "mixture").exists())
        self.assertEqual(list(self.root.glob(".ai-mixture-*")), [])

    def test_missing_token_pointer_or_noninteger_counts_fail(self):
        self.recipe["budget"] = {"unit": "tokens", "value": 10}
        with self.assertRaisesRegex(ValueError, "JSON pointer"):
            self.compose()
        self.recipe["budget"]["token_count"] = "/metadata/token_count"
        self.recipe["sources"] = [self.source("bad-tokens", 1, tokens=True)]
        with self.assertRaisesRegex(ValueError, "positive integer"):
            self.compose()

    def test_source_revision_pin_and_bytes_are_checked(self):
        self.recipe["sources"][0]["release_id"] = "another-release"
        with self.assertRaisesRegex(ValueError, "pinned release"):
            self.compose()
        path = self.root / "a/release/manifest.json"
        self.recipe["sources"][0]["release_id"] = json.loads(path.read_text())["release_id"]
        with (self.root / "a/release/train.jsonl").open("a") as stream:
            stream.write("\n")
        with self.assertRaisesRegex(ValueError, "hash/size mismatch"):
            self.compose()

    def test_source_mutation_during_composition_does_not_publish(self):
        from ai_data.composition import _Source
        original = _Source.take
        changed = False

        def mutate_after_read(source, *args):
            nonlocal changed
            result = original(source, *args)
            if not changed:
                with source.path.open("ab") as stream:
                    stream.write(b"\n")
                changed = True
            return result

        with patch.object(_Source, "take", mutate_after_read):
            with self.assertRaisesRegex(ValueError, "changed during composition"):
                self.compose()
        self.assertFalse((self.root / "mixture").exists())

    def test_empty_source_policies(self):
        self.recipe["sources"].append(self.source("empty", 0))
        result = self.compose()
        self.assertEqual(result["counts"]["records"], 25)
        self.recipe["exhaustion"] = "stop"
        result = self.compose("empty-stop")
        self.assertEqual(result["counts"]["records"], 0)
        self.assertEqual(self.read("empty-stop"), [])
        self.assertTrue(verify_mixture(self.root / "empty-stop")["ok"])
        self.recipe["exhaustion"] = "repeat"
        with self.assertRaisesRegex(ValueError, "nonempty"):
            self.compose("repeat")

    def test_corrupted_index_and_shard_are_detected(self):
        result = self.compose()
        path = self.root / "mixture" / result["shards"][0]["index_path"]
        path.write_bytes(path.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError, "hash/size mismatch"):
            verify_mixture(self.root / "mixture")
        self.compose("second")
        path = self.root / "second" / result["shards"][0]["path"]
        path.write_bytes(path.read_bytes().replace(b"authored", b"changed", 1))
        with self.assertRaisesRegex(ValueError, "hash/size mismatch"):
            MixtureReader(self.root / "second", verify=True)

    def test_existing_output_and_other_writer_lock_are_preserved(self):
        self.compose()
        path = self.root / "mixture/manifest.json"
        before = path.read_bytes()
        with self.assertRaises(FileExistsError):
            self.compose()
        self.assertEqual(path.read_bytes(), before)
        lock = self.root / ".second.lock"
        lock.write_text("other-writer")
        with self.assertRaises(FileExistsError):
            self.compose("second")
        self.assertEqual(lock.read_text(), "other-writer")

    def test_sequential_source_order_and_partial_final_shard(self):
        self.recipe["sources"] = [self.sources[0]]
        self.recipe.update(shuffle=False, shard_records=10)
        result = self.compose()
        self.assertEqual([row["source"]["position"] for row in self.read()], list(range(17)))
        self.assertEqual([shard["records"] for shard in result["shards"]], [10, 7])

    def test_source_manifest_and_partition_are_explicit(self):
        self.recipe["sources"][0]["path"] = "../elsewhere"
        with self.assertRaisesRegex(ValueError, "escapes"):
            self.compose()
        self.recipe["sources"][0]["path"] = "a/release"
        self.recipe["sources"][0]["split"] = "validation"
        result = self.compose()
        self.assertEqual(result["counts"]["source_records"], {"b": 11})


if __name__ == "__main__":
    unittest.main()
