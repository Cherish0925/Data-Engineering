"""A small envelope; domain payloads retain their own semantics."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

SPLITS = ("train", "validation", "test")
USES = ("train", "evaluate", "retrieve", "analyze", "redistribute")


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(dumps(value).encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def confined(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("path must be nonempty and relative to the workspace")
    root = root.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("path escapes the workspace")
    return path


def strict_json(text: str) -> Any:
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    def constant(value):
        raise ValueError(f"non-finite JSON number: {value}")

    value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    dumps(value)  # Also rejects numeric overflow such as 1e999.
    return value


def object_only(value: Any, required: set[str], optional: set[str], name: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    missing, extra = required - value.keys(), value.keys() - required - optional
    if missing or extra:
        raise ValueError(f"{name}: missing={sorted(missing)}, unknown={sorted(extra)}")


def nonempty(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")


def validate_record(record: Any) -> dict:
    object_only(record, {"schema_version", "id", "kind", "payload", "source", "split_group", "allowed_uses"},
                {"parents", "split", "metadata"}, "record")
    if record["schema_version"] != "1.0":
        raise ValueError("unsupported record schema_version")
    for key in ("id", "kind", "split_group"):
        nonempty(record[key], key)
    if not re.fullmatch(r"[a-z][a-z0-9_.-]*", record["kind"]):
        raise ValueError("kind must be a lowercase profile name")
    if not isinstance(record["payload"], dict) or not isinstance(record.get("metadata", {}), dict):
        raise ValueError("payload and metadata must be objects")
    object_only(record["source"], {"uri", "revision"}, set(), "source")
    for key in ("uri", "revision"):
        nonempty(record["source"][key], f"source.{key}")
    for key in ("allowed_uses", "parents"):
        values = record.get(key, [])
        if not isinstance(values, list):
            raise ValueError(f"{key} must be a list")
        for value in values:
            nonempty(value, key)
        if len(values) != len(set(values)):
            raise ValueError(f"{key} contains duplicates")
    if not set(record["allowed_uses"]).issubset(USES):
        raise ValueError("unknown allowed use")
    if record.get("split") is not None and record["split"] not in SPLITS:
        raise ValueError("unknown split")
    if record["id"] in record.get("parents", []):
        raise ValueError("record cannot be its own parent")
    # Deep copy makes caller mutation and non-JSON objects fail at the boundary.
    return strict_json(dumps(record))


def validate_recipe(recipe: Any) -> dict:
    object_only(recipe, {"schema_version", "name", "sources", "use", "seed", "splits"}, set(), "recipe")
    if recipe["schema_version"] != "1.0":
        raise ValueError("unsupported recipe schema_version")
    nonempty(recipe["name"], "name")
    nonempty(recipe["seed"], "seed")
    if recipe["use"] not in USES:
        raise ValueError("unknown recipe use")
    if not isinstance(recipe["sources"], list) or not recipe["sources"]:
        raise ValueError("sources must be a nonempty list")
    for source in recipe["sources"]:
        if not isinstance(source, dict):
            raise ValueError("source must be an object")
        nonempty(source.get("path"), "source.path")
        nonempty(source.get("connector"), "source.connector")
    object_only(recipe["splits"], set(SPLITS), set(), "splits")
    values = list(recipe["splits"].values())
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in values):
        raise ValueError("split weights must be finite numbers in [0, 1]")
    if not math.isclose(sum(values), 1.0, rel_tol=0, abs_tol=1e-12):
        raise ValueError("split weights must sum to one")
    return strict_json(dumps(recipe))


def record_schema() -> dict:
    text = {"type": "string", "minLength": 1, "pattern": "\\S"}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "AI Data Record 1.0", "type": "object", "additionalProperties": False,
        "required": ["schema_version", "id", "kind", "payload", "source", "split_group", "allowed_uses"],
        "properties": {
            "schema_version": {"const": "1.0"}, "id": text,
            "kind": {"type": "string", "pattern": "^[a-z][a-z0-9_.-]*$"},
            "payload": {"type": "object"}, "metadata": {"type": "object"},
            "source": {"type": "object", "additionalProperties": False, "required": ["uri", "revision"],
                       "properties": {"uri": text, "revision": text}},
            "split_group": text, "split": {"enum": [*SPLITS, None]},
            "parents": {"type": "array", "items": text, "uniqueItems": True},
            "allowed_uses": {"type": "array", "items": {"enum": list(USES)}, "uniqueItems": True},
        },
    }
