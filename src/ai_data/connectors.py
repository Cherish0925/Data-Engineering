"""Local readers and an explicit opt-in entry point for trusted connectors."""

from __future__ import annotations

import math
from importlib.metadata import entry_points
from pathlib import Path

from .contracts import confined, digest, nonempty, object_only, strict_json


def json_lines(path: Path):
    with path.open(encoding="utf-8-sig") as stream:
        for index, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                yield strict_json(line)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{path.name}:{index}: {exc}") from exc


def read_records(source: dict, root: Path):
    object_only(source, {"connector", "path"}, set(), "jsonl source")
    yield from json_lines(confined(root, source["path"]))


def read_gym(source: dict, root: Path):
    object_only(source, {"connector", "path", "uri", "revision", "allowed_uses"}, set(), "gym-jsonl source")
    for key in ("uri", "revision"):
        nonempty(source[key], key)
    for episode in json_lines(confined(root, source["path"])):
        if not isinstance(episode, dict) or type(episode.get("schema_version")) is not int or episode["schema_version"] != 1:
            raise ValueError("gym-jsonl requires export schema_version 1")
        for key in ("episode_id", "task", "agent", "status", "reward", "verification", "trajectory"):
            if key not in episode:
                raise ValueError(f"gym episode missing {key}")
        nonempty(episode["episode_id"], "episode_id")
        task = episode["task"]
        object_only(task, {"family", "version", "seed", "split", "difficulty"}, set(), "gym task")
        nonempty(task["family"], "task.family")
        if task["split"] not in ("train", "validation", "test"):
            raise ValueError("invalid Gym split")
        for key, minimum in (("version", 1), ("seed", 0), ("difficulty", 1)):
            if type(task[key]) is not int or task[key] < minimum:
                raise ValueError(f"invalid Gym task.{key}")
        if task["difficulty"] not in (1, 2, 3):
            raise ValueError("invalid Gym difficulty")
        if not isinstance(episode["trajectory"], list):
            raise ValueError("Gym trajectory must be a list")
        reward = episode["reward"]
        if episode["status"] in ("passed", "failed"):
            if type(reward) not in (int, float) or not math.isfinite(reward) or not 0 <= reward <= 1:
                raise ValueError("scored Gym episode must have a finite reward in [0, 1]")
        elif reward is not None:
            raise ValueError("unscored Gym episode must retain a null reward")
        # Keep different agents/retries/difficulties on the same task seed together.
        group = {key: task[key] for key in ("family", "version", "split", "seed")}
        yield {
            "schema_version": "1.0", "id": f"gym:{episode['episode_id']}", "kind": "trajectory",
            "payload": episode, "source": {"uri": source["uri"], "revision": source["revision"]},
            "split_group": f"gym:{digest(group)}", "split": task["split"],
            "allowed_uses": source["allowed_uses"],
            "metadata": {"adapter": "verifiable-agent-gym/export-v1", "scored": reward is not None},
        }


BUILTINS = {"jsonl": read_records, "gym-jsonl": read_gym}


def resolve_reader(name: str, *, allow_plugins: bool = False):
    if name in BUILTINS:
        return BUILTINS[name], {"name": name, "provider": "ai-data-engineering"}
    if not allow_plugins:
        raise ValueError(f"connector {name!r} is not built in; trusted plugins require --allow-plugins")
    matches = list(entry_points(group="ai_data.connectors", name=name))
    if len(matches) != 1:
        raise ValueError(f"expected one installed connector named {name!r}, found {len(matches)}")
    point = matches[0]
    reader = point.load()
    if not callable(reader):
        raise ValueError("connector must be callable")
    return reader, {"name": name, "provider": point.dist.name if point.dist else "unknown",
                    "version": point.dist.version if point.dist else "unknown", "entry_point": point.value}
