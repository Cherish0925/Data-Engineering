"""Task release -> grouped SQL episodes -> trajectory release -> trainer shards.

Install both repositories. The two scripted policies exercise correct/incorrect
outcomes; replace their actions with a model policy for a learning experiment.
"""

import argparse
import json
from pathlib import Path
import shutil

from ai_data import build, compose, MixtureReader, verify_mixture
from agent_gym.rollout import PolicyVersion, RolloutBatch, export_rollouts
from agent_gym.suite import TaskSuite
from agent_gym.taskpacks import load_taskpack


QUERIES = {
    "sql:october-region-revenue": "WITH bills AS (SELECT order_id,SUM(quantity*unit_price) revenue FROM order_items GROUP BY order_id) SELECT region,SUM(revenue) total FROM bills JOIN orders USING(order_id) JOIN customers USING(customer_id) WHERE status='completed' AND ordered_at BETWEEN '2026-10-01' AND '2026-10-31' GROUP BY region ORDER BY total DESC,region",
    "sql:repeat-customer-spend": "SELECT c.name,SUM(i.quantity*i.unit_price) FROM customers c JOIN orders o USING(customer_id) JOIN order_items i USING(order_id) WHERE o.status='completed' AND c.customer_id IN (SELECT customer_id FROM orders WHERE status='completed' GROUP BY customer_id HAVING COUNT(*)>=2) GROUP BY c.customer_id,c.name",
}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(tasks: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(tasks, output / "tasks.jsonl")
    task_recipe = {"schema_version": "1.0", "name": "sql-task-source",
                   "sources": [{"connector": "jsonl", "path": "tasks.jsonl"}], "use": "analyze",
                   "seed": "cycle-1", "splits": {"train": 0.8, "validation": 0.1, "test": 0.1}}
    write_json(output / "tasks.recipe.json", task_recipe)
    task_manifest = build(output / "tasks.recipe.json", output / "task-release")
    pack = load_taskpack(output / "task-release", family="warehouse-sql")
    suite = TaskSuite(pack.specs("train"), attempts_per_task=4, name="sql-training",
                      metadata={"taskpack": pack.describe()})
    suite.save(output / "suite.json")
    sampler = suite.sampler(seed=17)
    with RolloutBatch(output / "episodes", slots=4, policy=PolicyVersion("scripted-sql", "1"),
                      task_factory=pack.make) as batch:
        while len(sampler):
            observations = batch.reset(dict(enumerate(sampler.take(4))))
            if any(response["done"] for response in observations.values()):
                raise RuntimeError("task setup failed")
            batch.step({slot: {"tool": "database_schema", "arguments": {}} for slot in observations})
            batch.step({slot: {"tool": "query", "arguments": {"sql": "SELECT status,COUNT(*) FROM orders GROUP BY status"}}
                        for slot in observations})
            actions = {}
            for slot, response in observations.items():
                task_id = response["rollout"]["data_reference"]["record_id"]
                query = QUERIES[task_id] if response["rollout"]["attempt"] % 2 == 0 else "SELECT 'incorrect',0"
                actions[slot] = {"submit": {"sql": query}}
            batch.step(actions)
        outcomes = batch.summary()
    exported = export_rollouts(output / "episodes", output / "trajectories.jsonl")
    trace_recipe = {"schema_version": "1.0", "name": "sql-experience",
                    "sources": [{"connector": "gym-jsonl", "path": "trajectories.jsonl",
                                 "uri": "example://sql-rollout-cycle", "revision": suite.suite_id,
                                 "allowed_uses": ["train", "evaluate", "analyze"]}],
                    "use": "train", "seed": "cycle-1", "splits": {"train": 0.8, "validation": 0.1, "test": 0.1}}
    write_json(output / "experience.recipe.json", trace_recipe)
    traces = build(output / "experience.recipe.json", output / "experience-release")
    recipe = {"schema_version": "1.0", "name": "sql-rollout-training",
              "sources": [{"name": "sql-rollouts", "path": "experience-release", "release_id": traces["release_id"],
                           "split": "train", "weight": 1}], "seed": "training-17",
              "budget": {"unit": "records", "value": exported}, "shard_records": 3, "exhaustion": "renormalize"}
    write_json(output / "mixture.recipe.json", recipe)
    mixture = compose(output / "mixture.recipe.json", output / "training")
    verified = verify_mixture(output / "training")
    rank_indices = []
    for rank in range(2):
        with MixtureReader(output / "training", rank=rank, world_size=2) as reader:
            rank_indices.append([sample["sample_index"] for sample in reader])
    assert not set(rank_indices[0]) & set(rank_indices[1])
    assert sorted(rank_indices[0] + rank_indices[1]) == list(range(exported))
    with MixtureReader(output / "training") as reader:
        next(reader)
        state = reader.state_dict()
        expected = next(reader)
    with MixtureReader(output / "training") as reader:
        reader.load_state_dict(state)
        assert next(reader) == expected
    samples = list(MixtureReader(output / "training"))
    groups = {s["record"]["payload"]["rollout"]["group_id"] for s in samples}
    assert all(s["record"]["payload"]["rollout"]["data_reference"]["release_id"] == task_manifest["release_id"]
               for s in samples)
    assert {s["record"]["payload"]["reward"] for s in samples} == {0.0, 1.0}
    result = {"task_release": task_manifest["release_id"], "suite_id": suite.suite_id,
              "outcomes": outcomes, "exported": exported, "groups": len(groups),
              "mixture": mixture["release_id"], "shards": verified["shards"],
              "rank_records": list(map(len, rank_indices)), "reader_restart": True}
    write_json(output / "result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gym-tasks", required=True, type=Path, help="Gym examples/sql-workload/tasks.jsonl")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.gym_tasks.resolve(), args.output.resolve()), indent=2))
