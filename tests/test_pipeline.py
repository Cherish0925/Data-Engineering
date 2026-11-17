import json
from pathlib import Path
import tempfile
import unittest

from ai_data.contracts import confined, dumps, record_schema, strict_json, validate_record
from ai_data.pipeline import build, profile, verify_release


def record(identifier, text=None, group=None, split=None, uses=None, parents=None):
    value = {"schema_version": "1.0", "id": identifier, "kind": "document",
             "payload": {"text": text or identifier}, "source": {"uri": "example://source", "revision": "1"},
             "split_group": group or identifier, "allowed_uses": ["train", "evaluate"] if uses is None else uses}
    if split is not None:
        value["split"] = split
    if parents is not None:
        value["parents"] = parents
    return value


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.recipe = {"schema_version": "1.0", "name": "test", "sources": [{"connector": "jsonl", "path": "source.jsonl"}],
                       "use": "train", "seed": "1", "splits": {"train": 0.8, "validation": 0.1, "test": 0.1}}

    def run_build(self, rows, name="release"):
        (self.root / "source.jsonl").write_text("".join(dumps(r) + "\n" for r in rows), encoding="utf-8")
        (self.root / "recipe.json").write_text(dumps(self.recipe), encoding="utf-8")
        return build(self.root / "recipe.json", self.root / name)

    def decisions(self, name="release"):
        return {r["id"]: r for r in map(json.loads, (self.root / name / "decisions.jsonl").read_text().splitlines())}

    def test_repeatable_release_and_integrity(self):
        rows = [record("a", "same", split="train"), record("b", "same"), record("c", uses=[])]
        a = self.run_build(rows)
        b = self.run_build(rows, "second")
        self.assertEqual(a["release_id"], b["release_id"])
        self.assertEqual(a["counts"]["decisions"], {"retained": 1, "duplicate": 1, "excluded": 1})
        self.assertTrue(verify_release(self.root / "release")["ok"])
        self.assertEqual(profile(self.root / "release/train.jsonl")["records"], 1)

    def test_filtered_duplicate_still_protects_holdout(self):
        self.run_build([record("heldout", "same", split="test", uses=["evaluate"]),
                        record("copy", "same"), record("derived", parents=["copy"])])
        self.assertEqual({r["split"] for r in self.decisions().values()}, {"test"})

    def test_transitive_duplicate_groups(self):
        self.run_build([record("a", "x", "one"), record("b", "x", "two"), record("c", "y", "two"),
                        record("d", "y", "three", split="validation")])
        self.assertEqual({r["split"] for r in self.decisions().values()}, {"validation"})

    def test_conflicting_holdout_is_not_silently_repaired(self):
        with self.assertRaisesRegex(ValueError, "conflicting fixed splits"):
            self.run_build([record("a", "same", split="train"), record("b", "same", split="test")])
        self.assertFalse((self.root / "release").exists())

    def test_shared_external_parent(self):
        self.run_build([record("a", parents=["external:book"], split="test"), record("b", parents=["external:book"])])
        self.assertEqual(self.decisions()["b"]["split"], "test")

    def test_different_annotations_and_sources_survive_dedup(self):
        a, b, c = record("a", "same"), record("b", "same"), record("c", "same")
        b["metadata"] = {"labeler": "second"}
        c["source"]["revision"] = "2"
        result = self.run_build([a, b, c])
        self.assertEqual(result["counts"]["retained"], 3)
        self.assertEqual(len({r["component"] for r in self.decisions().values()}), 1)

    def test_input_order_does_not_change_assignments(self):
        rows = [record(str(i), group=str(i // 3)) for i in range(30)]
        self.run_build(rows)
        first = self.decisions()
        self.run_build(list(reversed(rows)), "second")
        self.assertEqual(first, self.decisions("second"))

    def test_invalid_records_and_json(self):
        for key, value in [("allowed_uses", ["oops"]), ("allowed_uses", "train"), ("payload", {"n": float("nan")}),
                           ("schema_version", "2.0"), ("split", "heldout"), ("id", " ")]:
            with self.subTest(key=key, value=value):
                bad = record("bad")
                bad[key] = value
                with self.assertRaises((ValueError, TypeError)):
                    validate_record(bad)
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}'):
            with self.assertRaises(ValueError):
                strict_json(text)

    def test_duplicate_ids_fail_without_writing(self):
        with self.assertRaisesRegex(ValueError, "duplicate record id"):
            self.run_build([record("a"), record("a", "different")])
        self.assertFalse((self.root / "release").exists())

    def test_existing_release_is_not_overwritten(self):
        self.run_build([record("a")])
        before = (self.root / "release/manifest.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_build([record("b")])
        self.assertEqual(before, (self.root / "release/manifest.json").read_bytes())

    def test_changed_files_or_manifest_fail(self):
        self.run_build([record("a", split="train")])
        file = self.root / "release/train.jsonl"
        file.write_text(file.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "hash/size mismatch"):
            verify_release(self.root / "release")
        self.run_build([record("a")], "second")
        path = self.root / "second/manifest.json"
        data = json.loads(path.read_text())
        data["name"] = "changed"
        path.write_text(dumps(data))
        with self.assertRaisesRegex(ValueError, "manifest hash mismatch"):
            verify_release(self.root / "second")

    def test_paths_and_plugins(self):
        with self.assertRaises(ValueError):
            confined(self.root, "../elsewhere")
        with self.assertRaises(ValueError):
            confined(self.root, str(self.root / "absolute"))
        self.recipe["sources"][0]["connector"] = "untrusted"
        with self.assertRaisesRegex(ValueError, "trusted plugins"):
            self.run_build([record("a")])

    def test_invalid_recipe(self):
        for weights in ({"train": 1, "validation": 1, "test": 1}, {"train": True, "validation": 0, "test": 0}):
            self.recipe["splits"] = weights
            with self.assertRaises(ValueError):
                self.run_build([record("a")])

    def test_schema_matches_examples(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("optional jsonschema is not installed")
        validator = Draft202012Validator(record_schema())
        for line in (Path(__file__).parents[1] / "examples/records.jsonl").read_text().splitlines():
            validator.validate(validate_record(json.loads(line)))

    def test_gym_scored_and_unscored(self):
        root = Path(__file__).parents[1] / "examples"
        result = build(root / "gym.recipe.json", self.root / "gym")
        self.assertEqual(result["counts"]["retained"], 2)
        train = json.loads((self.root / "gym/train.jsonl").read_text())
        test = json.loads((self.root / "gym/test.jsonl").read_text())
        self.assertEqual(train["payload"]["reward"], 1.0)
        self.assertIsNone(test["payload"]["reward"])
        self.assertFalse(test["metadata"]["scored"])
        self.assertTrue(verify_release(self.root / "gym")["ok"])

    def test_unscored_reward_is_not_relabelled(self):
        from ai_data.connectors import read_gym
        rows = (Path(__file__).parents[1] / "examples/gym-export.jsonl").read_text().splitlines()
        bad = json.loads(rows[1])
        bad["reward"] = 0
        (self.root / "bad.jsonl").write_text(dumps(bad))
        with self.assertRaisesRegex(ValueError, "null reward"):
            list(read_gym({"connector": "gym-jsonl", "path": "bad.jsonl", "uri": "example://gym",
                           "revision": "1", "allowed_uses": ["analyze"]}, self.root))


if __name__ == "__main__":
    unittest.main()
