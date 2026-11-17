"""Deterministic reference builder. All front ends call these functions."""

from __future__ import annotations

from collections import Counter, defaultdict
import os
from pathlib import Path
import shutil
import tempfile

from .connectors import json_lines, resolve_reader
from . import __version__
from .contracts import SPLITS, confined, digest, dumps, file_digest, strict_json, validate_recipe, validate_record


def profile(path: str | Path) -> dict:
    counts, uses, seen = Counter(), Counter(), set()
    rows = 0
    for value in json_lines(Path(path)):
        record = validate_record(value)
        if record["id"] in seen:
            raise ValueError(f"duplicate record id: {record['id']}")
        seen.add(record["id"])
        counts[record["kind"]] += 1
        uses.update(record["allowed_uses"])
        rows += 1
    return {"records": rows, "kinds": dict(counts), "allowed_uses": dict(uses)}


def _partition(records: list[dict], recipe: dict) -> tuple[dict, dict]:
    # Union records BEFORE filtering/deduplication, so a filtered bridge or
    # held-out duplicate cannot silently move its derivatives into training.
    parent = {}

    def find(node):
        parent.setdefault(node, node)
        root = node
        while parent[root] != root:
            root = parent[root]
        while parent[node] != node:
            previous = node
            node = parent[node]
            parent[previous] = root
        return root

    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[max(a, b)] = min(a, b)

    fingerprints = {}
    for r in records:
        node = "id:" + r["id"]
        fingerprint = digest({"kind": r["kind"], "payload": r["payload"]})
        fingerprints[r["id"]] = fingerprint
        union(node, "group:" + r["split_group"])
        union(node, "content:" + fingerprint)
        for ancestor in r.get("parents", []):
            union(node, "id:" + ancestor)
    components = defaultdict(list)
    for r in records:
        components[find("id:" + r["id"])].append(r)
    assignments = {}
    for members in components.values():
        fixed = {r["split"] for r in members if r.get("split") is not None}
        if len(fixed) > 1:
            raise ValueError("related records have conflicting fixed splits: " + ", ".join(sorted(r["id"] for r in members)))
        groups = sorted({r["split_group"] for r in members})
        component = digest(groups)
        if fixed:
            split = next(iter(fixed))
        else:
            u = int(digest({"seed": recipe["seed"], "groups": groups}), 16) / (1 << 256)
            threshold, split = 0.0, "test"
            for candidate in SPLITS:
                threshold += recipe["splits"][candidate]
                if u < threshold:
                    split = candidate
                    break
        for r in members:
            assignments[r["id"]] = {"split": split, "component": component}
    return assignments, fingerprints


def build(recipe_path: str | Path, output: str | Path, *, root: str | Path | None = None,
          allow_plugins: bool = False) -> dict:
    recipe_path, output = Path(recipe_path).resolve(), Path(output).resolve()
    root = Path(root).resolve() if root is not None else recipe_path.parent
    recipe = validate_recipe(strict_json(recipe_path.read_text(encoding="utf-8")))
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    records, inputs, providers, ids = [], [], [], set()
    for source in recipe["sources"]:
        path = confined(root, source["path"])
        if path == output or path.is_relative_to(output):
            raise ValueError("output must not contain an input")
        before = file_digest(path)
        reader, provider = resolve_reader(source["connector"], allow_plugins=allow_plugins)
        for raw in reader(source, root):
            record = validate_record(raw)
            if record["id"] in ids:
                raise ValueError(f"duplicate record id: {record['id']}")
            ids.add(record["id"])
            records.append(record)
        if file_digest(path) != before:
            raise ValueError("input changed while reading")
        inputs.append({"source": source, "sha256": before, "bytes": path.stat().st_size})
        providers.append(provider)
    records.sort(key=lambda r: r["id"])
    assignments, fingerprints = _partition(records, recipe)
    retained, decisions, groups = [], [], defaultdict(list)
    for record in records:
        identifier = record["id"]
        base = {"id": identifier, **assignments[identifier], "source": record["source"]}
        if recipe["use"] not in record["allowed_uses"]:
            decisions.append({**base, "decision": "excluded", "reason": "use_not_declared"})
        else:
            # Provenance/rights/annotations are semantically significant. Only
            # collapse exact payloads when their metadata and declarations match.
            key = digest({"content": fingerprints[identifier], "source": record["source"],
                          "allowed_uses": sorted(record["allowed_uses"]), "metadata": record.get("metadata", {})})
            groups[key].append(record)
    lineage = []
    for members in groups.values():
        representative = members[0]
        chosen = representative["id"]
        retained.append({**representative, "split": assignments[chosen]["split"]})
        lineage.append({"output_id": chosen, "input_ids": [r["id"] for r in members],
                        "parents": sorted({p for r in members for p in r.get("parents", [])}),
                        "source": representative["source"]})
        for r in members:
            decisions.append({"id": r["id"], **assignments[r["id"]], "source": r["source"],
                              "decision": "retained" if r["id"] == chosen else "duplicate",
                              "output_id": chosen})
    retained.sort(key=lambda r: r["id"])
    decisions.sort(key=lambda r: r["id"])
    lineage.sort(key=lambda r: r["output_id"])
    counts = {split: sum(r["split"] == split for r in retained) for split in SPLITS}
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".ai-data-", dir=output.parent))
    lock = output.parent / ("." + output.name + ".lock")
    locked = False
    try:
        # Serialize cooperating writers; never replace an existing release.
        with lock.open("x", encoding="utf-8") as stream:
            stream.write(str(os.getpid()))
        locked = True
        if output.exists():
            raise FileExistsError(f"output already exists: {output}")
        for name, rows in [(f"{split}.jsonl", [r for r in retained if r["split"] == split]) for split in SPLITS] + [
            ("decisions.jsonl", decisions), ("lineage.jsonl", lineage)
        ]:
            with (staging / name).open("w", encoding="utf-8", newline="\n") as stream:
                for row in rows:
                    stream.write(dumps(row) + "\n")
        files = {p.name: {"sha256": file_digest(p), "bytes": p.stat().st_size} for p in sorted(staging.iterdir())}
        implementation = {p.name: file_digest(p) for p in sorted(Path(__file__).parent.glob("*.py"))}
        manifest = {
            "schema_version": "1.0", "name": recipe["name"], "recipe": recipe,
            "builder": {"name": "ai-data-engineering", "version": __version__, "source_sha256": digest(implementation)},
            "connectors": providers, "inputs": inputs, "files": files,
            "counts": {"input": len(records), "retained": len(retained), "splits": counts,
                       "decisions": dict(Counter(r["decision"] for r in decisions))},
            "external_artifacts": "references_only_not_fetched_or_verified",
        }
        manifest["release_id"] = digest(manifest)
        (staging / "manifest.json").write_text(dumps(manifest) + "\n", encoding="utf-8", newline="\n")
        if output.exists():
            raise FileExistsError(f"output already exists: {output}")
        staging.rename(output)
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if locked:
            lock.unlink()


def inspect_release(path: str | Path) -> dict:
    return strict_json((Path(path) / "manifest.json").read_text(encoding="utf-8"))


def verify_release(path: str | Path) -> dict:
    root = Path(path).resolve()
    manifest = inspect_release(root)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "1.0":
        raise ValueError("unsupported release manifest")
    release_id = manifest.get("release_id")
    if digest({k: v for k, v in manifest.items() if k != "release_id"}) != release_id:
        raise ValueError("manifest hash mismatch")
    expected = {"train.jsonl", "validation.jsonl", "test.jsonl", "decisions.jsonl", "lineage.jsonl"}
    if set(manifest.get("files", {})) != expected:
        raise ValueError("release file set mismatch")
    ids, actual = set(), {}
    for name, info in manifest["files"].items():
        file = confined(root, name)
        if file_digest(file) != info["sha256"] or file.stat().st_size != info["bytes"]:
            raise ValueError(f"file hash/size mismatch: {name}")
        if name in {s + ".jsonl" for s in SPLITS}:
            split, count = name[:-6], 0
            for raw in json_lines(file):
                record = validate_record(raw)
                if record.get("split") != split or record["id"] in ids:
                    raise ValueError("invalid or duplicate record partition")
                if manifest["recipe"]["use"] not in record["allowed_uses"]:
                    raise ValueError("release contains an ineligible record")
                ids.add(record["id"])
                count += 1
            actual[split] = count
    if actual != manifest["counts"]["splits"] or len(ids) != manifest["counts"]["retained"]:
        raise ValueError("release count mismatch")
    return {"ok": True, "release_id": release_id, "records": len(ids), "files": len(expected),
            "external_artifacts": manifest["external_artifacts"]}
