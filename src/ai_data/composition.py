"""Pinned mixtures, streamed shards and checkpointable distributed readers."""

from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from fractions import Fraction
import hashlib
import math
import os
from pathlib import Path
import shutil
import struct
import tempfile

from .contracts import SPLITS, confined, digest, dumps, file_digest, nonempty, object_only, strict_json, validate_record

_U64 = struct.Struct("<Q")


def _positive_int(value, name):
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _manifest(root: Path, expected_id: str | None = None) -> dict:
    value = strict_json((root / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != "1.0":
        raise ValueError("unsupported release manifest")
    release_id = value.get("release_id")
    if digest({k: v for k, v in value.items() if k != "release_id"}) != release_id:
        raise ValueError("release manifest hash mismatch")
    if expected_id is not None and expected_id != release_id:
        raise ValueError("source release_id does not match the pinned release")
    return value


def _recipe(value: dict) -> dict:
    object_only(value, {"schema_version", "name", "sources", "seed", "budget", "shard_records", "exhaustion"},
                {"shuffle"}, "mixture recipe")
    if value["schema_version"] != "1.0":
        raise ValueError("unsupported mixture recipe schema_version")
    nonempty(value["name"], "name")
    nonempty(value["seed"], "seed")
    _positive_int(value["shard_records"], "shard_records")
    if value["exhaustion"] not in ("stop", "renormalize", "repeat"):
        raise ValueError("exhaustion must be stop, renormalize or repeat")
    if type(value.get("shuffle", True)) is not bool:
        raise ValueError("shuffle must be boolean")
    object_only(value["budget"], {"unit", "value"}, {"token_count"}, "budget")
    budget = value["budget"]
    _positive_int(budget["value"], "budget.value")
    if budget["unit"] not in ("records", "tokens"):
        raise ValueError("budget.unit must be records or tokens")
    if budget["unit"] == "tokens":
        pointer = budget.get("token_count")
        if not isinstance(pointer, str) or not pointer.startswith("/"):
            raise ValueError("token budgets require an explicit JSON pointer in budget.token_count")
    elif "token_count" in budget:
        raise ValueError("token_count applies only to a token budget")
    if not isinstance(value["sources"], list) or not value["sources"]:
        raise ValueError("sources must be a nonempty list")
    names = set()
    for source in value["sources"]:
        object_only(source, {"name", "path", "release_id", "split", "weight"}, set(), "mixture source")
        for field in ("name", "path", "release_id"):
            nonempty(source[field], field)
        if source["name"] in names:
            raise ValueError("mixture source names must be unique")
        names.add(source["name"])
        if source["split"] not in SPLITS:
            raise ValueError("unknown source split")
        weight = source["weight"]
        if type(weight) not in (int, float) or weight <= 0 or (isinstance(weight, float) and not math.isfinite(weight)):
            raise ValueError("source weights must be finite positive numbers")
    return strict_json(dumps(value))


def _units(record: dict, budget: dict) -> int:
    if budget["unit"] == "records":
        return 1
    value = record
    try:
        for raw in budget["token_count"].split("/")[1:]:
            key = raw.replace("~1", "/").replace("~0", "~")
            value = value[int(key)] if isinstance(value, list) else value[key]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError(f"record {record.get('id')!r} has no supplied token count at {budget['token_count']}") from exc
    _positive_int(value, "supplied token count")
    return value


def _permutation(position: int, count: int, key: str) -> int:
    """Cycle-walk a keyed Feistel bijection; no corpus-sized shuffle array."""
    if count <= 1:
        return 0
    bits = ((count - 1).bit_length() + 1) // 2
    mask = (1 << bits) - 1
    value = position
    while True:
        left, right = value >> bits, value & mask
        for round_index in range(6):
            block = hashlib.sha256(f"{key}:{round_index}:{right}".encode()).digest()
            left, right = right, left ^ (int.from_bytes(block, "big") & mask)
        value = (left << bits) | right
        if value < count:
            return value


def _pick(weights: list[int], seed: str, position: int) -> int:
    total = sum(weights)
    bits = total.bit_length()
    words = (bits + 255) // 256
    attempt = 0
    while True:
        raw = b"".join(hashlib.sha256(f"{seed}:{position}:{attempt}:{word}".encode()).digest() for word in range(words))
        choice = int.from_bytes(raw, "big") & ((1 << bits) - 1)
        if choice < total:
            break
        attempt += 1
    for index, weight in enumerate(weights):
        if choice < weight:
            return index
        choice -= weight
    raise AssertionError("weighted draw out of range")


def _read_at(data, index, position: int) -> dict:
    index.seek(position * _U64.size)
    raw = index.read(2 * _U64.size)
    if len(raw) != 2 * _U64.size:
        raise ValueError("record offset index is incomplete")
    start, end = struct.unpack("<QQ", raw)
    if end <= start:
        raise ValueError("record offsets are not increasing")
    data.seek(start)
    encoded = data.read(end - start)
    if len(encoded) != end - start:
        raise ValueError("record data is incomplete")
    return strict_json(encoded.decode("utf-8"))


class _Source:
    def __init__(self, spec: dict, root: Path, index_path: Path, budget: dict):
        self.spec, self.cursor, self.cycle = spec, 0, 0
        self.data = self.index = None
        release_root = confined(root, spec["path"])
        manifest = _manifest(release_root, spec["release_id"])
        name = spec["split"] + ".jsonl"
        if manifest.get("format") is not None or name not in manifest.get("files", {}):
            raise ValueError("mixture sources must be canonical partition releases")
        path = confined(release_root, name)
        self.path = path
        info = manifest["files"][name]
        hasher, count, offset = hashlib.sha256(), 0, 0
        with path.open("rb") as stream, index_path.open("wb") as offsets:
            for line in stream:
                start = offset
                hasher.update(line)
                offset += len(line)
                if not line.strip():
                    continue
                record = validate_record(strict_json(line.decode("utf-8")))
                if record.get("split") != spec["split"]:
                    raise ValueError("source record has the wrong partition")
                if manifest["recipe"]["use"] not in record["allowed_uses"]:
                    raise ValueError("source record has inconsistent declared use")
                _units(record, budget)
                offsets.write(_U64.pack(start))
                count += 1
            offsets.write(_U64.pack(offset))
        if hasher.hexdigest() != info["sha256"] or offset != info["bytes"]:
            raise ValueError("source partition hash/size mismatch")
        if count != manifest["counts"]["splits"][spec["split"]]:
            raise ValueError("source partition count mismatch")
        self.count = count
        self.identity = {"name": spec["name"], "release_id": spec["release_id"], "split": spec["split"],
                         "records": count, "sha256": hasher.hexdigest(), "bytes": offset}
        self.data, self.index = path.open("rb"), index_path.open("rb")

    def take(self, seed: str, shuffle: bool) -> tuple[dict, int]:
        if self.cursor == self.count:
            self.cursor = 0
            self.cycle += 1
        key = digest({"seed": seed, "source": self.spec["name"], "release_id": self.spec["release_id"], "cycle": self.cycle})
        position = _permutation(self.cursor, self.count, key) if shuffle else self.cursor
        record = _read_at(self.data, self.index, position)
        self.cursor += 1
        return record, position

    def close(self):
        for stream in (self.data, self.index):
            if stream is not None:
                stream.close()


class _Shards:
    def __init__(self, root: Path, limit: int):
        self.root, self.limit = root, limit
        self.items, self.total, self.rows, self.offset = [], 0, 0, 0
        self.data = self.index = None

    def append(self, sample: dict):
        if self.data is None:
            stem = f"shard-{len(self.items):06d}"
            self.names = (stem + ".jsonl", stem + ".idx")
            self.data = (self.root / self.names[0]).open("wb")
            self.index = (self.root / self.names[1]).open("wb")
            self.rows, self.offset = 0, 0
        encoded = (dumps(sample) + "\n").encode("utf-8")
        self.index.write(_U64.pack(self.offset))
        self.data.write(encoded)
        self.offset += len(encoded)
        self.rows += 1
        self.total += 1
        if self.rows == self.limit:
            self.finish()

    def finish(self):
        if self.data is None:
            return
        self.index.write(_U64.pack(self.offset))
        self.data.close()
        self.index.close()
        path, index_path = (self.root / name for name in self.names)
        self.items.append({"path": self.names[0], "index_path": self.names[1],
                           "first_index": self.total - self.rows, "records": self.rows,
                           "sha256": file_digest(path), "bytes": path.stat().st_size,
                           "index_sha256": file_digest(index_path), "index_bytes": index_path.stat().st_size})
        self.data = self.index = None

    def close(self):
        for stream in (self.data, self.index):
            if stream is not None:
                stream.close()


def compose(recipe_path: str | Path, output: str | Path, *, root: str | Path | None = None) -> dict:
    """Materialize a weighted, indexed mixture without loading its corpora into RAM."""
    recipe_path, output = Path(recipe_path).resolve(), Path(output).resolve()
    root = Path(root).resolve() if root is not None else recipe_path.parent
    recipe = _recipe(strict_json(recipe_path.read_text(encoding="utf-8")))
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".ai-mixture-", dir=output.parent))
    lock = output.parent / ("." + output.name + ".lock")
    sources, locked, writer = [], False, _Shards(staging, recipe["shard_records"])
    try:
        with lock.open("x", encoding="utf-8") as stream:
            stream.write(str(os.getpid()))
        locked = True
        if output.exists():
            raise FileExistsError(f"output already exists: {output}")
        scratch = staging / "source-indexes"
        scratch.mkdir()
        for index, spec in enumerate(recipe["sources"]):
            sources.append(_Source(spec, root, scratch / f"{index}.idx", recipe["budget"]))
        if recipe["exhaustion"] == "repeat" and any(source.count == 0 for source in sources):
            raise ValueError("repeat requires every source partition to be nonempty")
        fractions = [Fraction(str(spec["weight"])) for spec in recipe["sources"]]
        denominator = math.lcm(*(weight.denominator for weight in fractions))
        weights = [int(weight * denominator) for weight in fractions]
        active = [i for i, source in enumerate(sources) if source.count]
        counts, used, stop_reason = Counter(), 0, "all_sources_exhausted"
        if recipe["exhaustion"] == "stop" and len(active) < len(sources):
            active, stop_reason = [], "source_exhausted"
        while active and used < recipe["budget"]["value"]:
            selected = active[_pick([weights[i] for i in active], recipe["seed"], writer.total)]
            source = sources[selected]
            record, position = source.take(recipe["seed"], recipe.get("shuffle", True))
            cost = _units(record, recipe["budget"])
            if used + cost > recipe["budget"]["value"]:
                stop_reason = "next_record_exceeds_budget"
                break
            writer.append({"sample_index": writer.total,
                           "source": {"name": source.spec["name"], "release_id": source.spec["release_id"],
                                      "split": source.spec["split"], "record_id": record["id"],
                                      "cycle": source.cycle, "position": position}, "record": record})
            counts[source.spec["name"]] += 1
            used += cost
            if used == recipe["budget"]["value"]:
                stop_reason = "budget_reached"
                break
            if source.cursor == source.count:
                if recipe["exhaustion"] == "stop":
                    stop_reason = "source_exhausted"
                    break
                if recipe["exhaustion"] == "renormalize":
                    active.remove(selected)
        writer.finish()
        for source in sources:
            if source.path.stat().st_size != source.identity["bytes"] or file_digest(source.path) != source.identity["sha256"]:
                raise ValueError("source partition changed during composition")
            source.close()
        shutil.rmtree(scratch)
        manifest = {
            "schema_version": "1.0", "format": "ai-data-mixture", "name": recipe["name"], "recipe": recipe,
            "builder": {"algorithm": "composition-v1", "source_sha256": digest({
                name: file_digest(Path(__file__).with_name(name)) for name in ("composition.py", "contracts.py")})},
            "sources": [source.identity for source in sources], "shards": writer.items,
            "sampling": {"unit": "record", "source_selection": "sha256-weighted-v1",
                         "source_order": "feistel-v1" if recipe.get("shuffle", True) else "original",
                         "exhaustion": recipe["exhaustion"]},
            "counts": {"records": writer.total, "budget_units": used, "source_records": dict(counts)},
            "stop_reason": stop_reason,
        }
        manifest["release_id"] = digest(manifest)
        (staging / "manifest.json").write_text(dumps(manifest) + "\n", encoding="utf-8", newline="\n")
        if output.exists():
            raise FileExistsError(f"output already exists: {output}")
        staging.rename(output)
        return manifest
    finally:
        writer.close()
        for source in sources:
            source.close()
        if staging.exists():
            shutil.rmtree(staging)
        if locked:
            lock.unlink()


def _mixture_manifest(root: Path) -> dict:
    manifest = _manifest(root)
    if manifest.get("format") != "ai-data-mixture":
        raise ValueError("not an indexed mixture release")
    count, paths = 0, set()
    for shard in manifest["shards"]:
        if shard["first_index"] != count or type(shard["records"]) is not int or shard["records"] <= 0:
            raise ValueError("mixture shard ranges are inconsistent")
        count += shard["records"]
        for name in (shard["path"], shard["index_path"]):
            confined(root, name)
            if name in paths:
                raise ValueError("mixture shard paths are repeated")
            paths.add(name)
        if shard["index_bytes"] != (shard["records"] + 1) * _U64.size:
            raise ValueError("mixture index size is inconsistent")
    if count != manifest["counts"]["records"]:
        raise ValueError("mixture total count is inconsistent")
    return manifest


def verify_mixture(path: str | Path) -> dict:
    """Check all mixture bytes, offsets and accounting using constant record memory."""
    root = Path(path).resolve()
    manifest = _mixture_manifest(root)
    sources = {source["name"]: source for source in manifest["sources"]}
    counts, used = Counter(), 0
    for shard in manifest["shards"]:
        data_path, index_path = confined(root, shard["path"]), confined(root, shard["index_path"])
        for file, sha, size in ((data_path, shard["sha256"], shard["bytes"]),
                                (index_path, shard["index_sha256"], shard["index_bytes"])):
            if file.stat().st_size != size or file_digest(file) != sha:
                raise ValueError(f"mixture shard hash/size mismatch: {file.name}")
        with data_path.open("rb") as data, index_path.open("rb") as index:
            if _U64.unpack(index.read(8))[0] != 0:
                raise ValueError("mixture index must begin at byte zero")
            index.seek(-8, os.SEEK_END)
            if _U64.unpack(index.read(8))[0] != shard["bytes"]:
                raise ValueError("mixture index must cover the complete shard")
            for position in range(shard["records"]):
                sample = _read_at(data, index, position)
                if sample["sample_index"] != shard["first_index"] + position:
                    raise ValueError("mixture sample order is inconsistent")
                record = validate_record(sample["record"])
                source = sample["source"]
                declared = sources.get(source["name"])
                if declared is None or source["release_id"] != declared["release_id"] or source["split"] != declared["split"]:
                    raise ValueError("mixture sample source does not match its manifest")
                if record["id"] != source["record_id"] or record.get("split") != source["split"]:
                    raise ValueError("mixture record identity is inconsistent")
                if type(source["position"]) is not int or not 0 <= source["position"] < declared["records"]:
                    raise ValueError("mixture source position is invalid")
                if type(source["cycle"]) is not int or source["cycle"] < 0:
                    raise ValueError("mixture source cycle is invalid")
                counts[source["name"]] += 1
                used += _units(record, manifest["recipe"]["budget"])
    if dict(counts) != manifest["counts"]["source_records"] or used != manifest["counts"]["budget_units"]:
        raise ValueError("mixture accounting mismatch")
    if used > manifest["recipe"]["budget"]["value"]:
        raise ValueError("mixture exceeds its budget")
    return {"ok": True, "release_id": manifest["release_id"], "records": sum(counts.values()),
            "budget_units": used, "shards": len(manifest["shards"])}


class MixtureReader:
    """Rank-strided indexed reads, with exact restart for a fixed worker topology.

    Each yield includes its canonical record and source/sample identity. No
    prefetch occurs, so state_dict records the exact next unconsumed sample.
    Call verify_mixture once before a run, or set verify=True on construction.
    """

    def __init__(self, path: str | Path, *, rank: int = 0, world_size: int = 1,
                 drop_remainder: bool = False, verify: bool = False):
        _positive_int(world_size, "world_size")
        if type(rank) is not int or not 0 <= rank < world_size:
            raise ValueError("rank must be an integer in [0, world_size)")
        if type(drop_remainder) is not bool:
            raise ValueError("drop_remainder must be boolean")
        self.root = Path(path).resolve()
        self.manifest = _mixture_manifest(self.root)
        if verify:
            verify_mixture(self.root)
        self.rank, self.world_size, self.consumed = rank, world_size, 0
        self.drop_remainder = drop_remainder
        self.total = self.manifest["counts"]["records"]
        if drop_remainder:
            self.total -= self.total % world_size
        self.starts = [s["first_index"] for s in self.manifest["shards"]]
        self._shard, self._data, self._index = None, None, None

    def __len__(self):
        return max(0, (self.total - self.rank + self.world_size - 1) // self.world_size)

    def __iter__(self):
        return self

    def __next__(self) -> dict:
        ordinal = self.rank + self.consumed * self.world_size
        if ordinal >= self.total:
            self.close()
            raise StopIteration
        shard_index = bisect_right(self.starts, ordinal) - 1
        shard = self.manifest["shards"][shard_index]
        if self._shard != shard_index:
            self.close()
            self._data = confined(self.root, shard["path"]).open("rb")
            self._index = confined(self.root, shard["index_path"]).open("rb")
            self._shard = shard_index
        sample = _read_at(self._data, self._index, ordinal - shard["first_index"])
        if sample.get("sample_index") != ordinal:
            raise ValueError("mixture sample index mismatch")
        self.consumed += 1
        return sample

    def state_dict(self) -> dict:
        return {"schema_version": "1.0", "release_id": self.manifest["release_id"],
                "rank": self.rank, "world_size": self.world_size,
                "drop_remainder": self.drop_remainder, "consumed": self.consumed}

    def load_state_dict(self, state: dict) -> None:
        object_only(state, {"schema_version", "release_id", "rank", "world_size", "drop_remainder", "consumed"}, set(), "reader state")
        expected = self.state_dict()
        if any(state[key] != expected[key] for key in ("schema_version", "release_id", "rank", "world_size", "drop_remainder")):
            raise ValueError("reader state belongs to a different release or worker topology")
        if type(state["consumed"]) is not int or not 0 <= state["consumed"] <= len(self):
            raise ValueError("invalid reader consumed count")
        self.close()
        self.consumed = state["consumed"]

    def close(self):
        for stream in (self._data, self._index):
            if stream is not None:
                stream.close()
        self._shard = self._data = self._index = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
