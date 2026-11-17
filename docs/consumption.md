# Dataset composition and training consumption

The data path has two operations. `build` constructs a canonical source release with grouping and lineage. `compose` consumes pinned source partitions and materializes a budgeted stream as indexed shards. A trainer reads those shards through `MixtureReader`.

## Compose a distribution

Run the complete text/code example:

```sh
python examples/compose_training.py --output runs/training-example
```

A mixture recipe identifies each source release, partition and sampling weight:

```json
{
  "schema_version": "1.0",
  "name": "text-code-training",
  "sources": [
    {"name": "text", "path": "text-release", "release_id": "<release-id>", "split": "train", "weight": 3},
    {"name": "code", "path": "code-release", "release_id": "<release-id>", "split": "train", "weight": 1}
  ],
  "seed": "training-17",
  "budget": {"unit": "records", "value": 100000},
  "shard_records": 4096,
  "exhaustion": "repeat",
  "shuffle": true
}
```

```sh
ai-data compose mixture.recipe.json --output runs/training
ai-data verify-mixture runs/training
```

Weights define probabilities of selecting a **record source**; realized counts are recorded. Token budgets use `{"unit":"tokens","value":1000000,"token_count":"/metadata/token_count"}`. Counts must come from an explicitly chosen tokenizer/encoder upstream. Token budgets stop before the next whole record would exceed the ceiling. Source weights remain record weights rather than token fractions.

| Exhaustion | Behavior |
| --- | --- |
| `stop` | Finish as soon as one source has supplied its last record. |
| `renormalize` | Remove exhausted sources and continue with the remaining weights. |
| `repeat` | Start a new deterministic source permutation each cycle until the budget is reached. |

Each sample retains its global sample index, source release/split, original record ID, source cycle/position and canonical record. Shards have JSONL payloads plus byte-offset indexes; manifests bind their hashes and realized source/budget counts.

## Consume and resume

```python
from ai_data import MixtureReader

with MixtureReader("runs/training", rank=0, world_size=4,
                   drop_remainder=True) as reader:
    for sample in reader:
        consume(sample["record"])
        data_state = reader.state_dict()
        # Save data_state together with the corresponding model/optimizer state.
```

Restore by constructing the same reader and calling `load_state_dict(data_state)`. Its next sample is exactly the next unconsumed sample at the saved cursor. State binds the release, rank, worker count and tail policy. A changed worker topology requires a new consumption plan.

Rank assignment is a disjoint stride through the global stream. Default behavior includes all records and may give ranks different lengths by one record. `drop_remainder=True` drops the global tail so all ranks receive equal counts. A framework using multiple DataLoader workers should map rank and worker ID to a single combined rank/worker count. Batch-size divisibility and optimizer checkpoints remain with the trainer.

The reader performs no prefetch. Consequently its cursor is explicit; consumers adding prefetch or gradient accumulation must checkpoint the corresponding queue/accumulation state. It exposes records and supplied annotations; tokenization, loss masks and tensor collation belong to the consumer adapter.

## Execution and scale

Composition scans and validates source bytes, builds source indexes on disk, samples by indexed reads, and streams output shards. Source bytes are checked again before publication. Memory grows with the largest record plus source/shard metadata. Composition runs locally; the rank-aware reader can be used by separate worker processes on shared files.

The original source `build` currently holds records in memory for connected-component grouping. Large upstream preparation should use a suitable existing backend and export the common release contract. The mixture path does not load the complete source corpus into memory. Its deterministic keyed permutation uses bounded state; it is not a claim of cryptographic randomness.

Reproduce the I/O exercise with `python examples/measure_composition.py --output runs/scale --records 10000 100000`. It records source/output sizes, composition time, peak RSS, verification and rank consumption in fresh processes. A Linux/Python 3.12 local run on 2026-11-17 produced:

| Input records | Input bytes | Output bytes | Compose seconds | Peak RSS, MiB |
| ---: | ---: | ---: | ---: | ---: |
| 10,000 | 7,546,670 | 9,713,364 | 0.930 | 17.234 |
| 100,000 | 75,766,670 | 97,733,540 | 12.368 | 17.211 |

Timing includes source validation and indexing, and excludes fixture preparation. Four rank readers each consumed 25,000 records from the larger release; their sequential reads took 2.216 seconds total. These are synthetic local I/O measurements, separate from model training throughput.

## Task and trajectory cycle

Install both repositories, then run from Data Engineering:

```sh
python -m pip install -e ../Verifiable-Agent-Gym
python examples/experience_cycle.py --gym-tasks ../Verifiable-Agent-Gym/examples/sql-workload/tasks.jsonl --output runs/experience-cycle
```

The example builds a task release, creates a Gym task suite, executes grouped multi-step SQL episodes, imports the factual trajectories, composes training shards, and checks two-rank coverage plus reader restart. It includes correct and incorrect scripted attempts so feedback survives the entire path. Replace the scripted action function with a model adapter and use the same interfaces for a learning experiment.
