# Integrations

All front ends share `ai_data.pipeline` and `ai_data.composition`. Source adapters produce records; consumer adapters turn released records into the inputs their workload needs.

## Implemented interfaces

| Interface | Current support |
| --- | --- |
| Python | `build`, `profile`, `inspect_release`, `verify_release`, `compose`, `verify_mixture`, `MixtureReader`. |
| CLI | `build`, `profile`, `inspect`, `verify`, `compose`, `verify-mixture`, `schema`, `connect`, `serve`; JSON stdout, errors on stderr with exit code 2. |
| MCP | Seven stdio tools over the same data operations, using the official Python SDK v1 and a configured filesystem workspace. |
| Skill | `skills/data-engineering/SKILL.md`, repository-scoped operating guidance for compatible agent hosts. |
| Connector plugin | Installed Python entry points under `ai_data.connectors`, enabled by SDK/CLI. |
| Canonical JSONL | Native reader for record schema `1.0`. |
| Verifiable Agent Gym | Task release input to Gym; episode/rollout export-v1 input from Gym. Original splits, policy/group identities and supplied model statistics survive the handoff. |

See [training consumption](consumption.md) for mixture recipes, rank assignment and reader checkpoints. MCP controls preparation and returns metadata; trainers consume shard files directly.

## Gym handoff

The adapter reads Gym episode export-v1, including the `rollout` and `policy_steps` extensions from Gym v0.2. Build task records with the `sql/v1` payload profile, then load that release through Gym's `load_taskpack`. The complete round trip runs in [`examples/experience_cycle.py`](../examples/experience_cycle.py).

```sh
agent-gym export runs/my-agent --output workspace/gym-export.jsonl --include-unscored
# For grouped RolloutBatch runs:
agent-gym export-rollouts runs/learner --output workspace/rollouts.jsonl
```

Create a recipe in `workspace` using connector `gym-jsonl`, the export's relative path, a source URI/revision and `allowed_uses`. The runnable import recipe is `examples/gym.recipe.json`.

The adapter preserves the whole exported payload. Records are grouped by task family, version, original split and seed, keeping difficulty variants, agents and attempts together. Scored `passed`/`failed` records carry a finite reward in [0,1]; unscored records retain null rewards. Consumer recipes define how each outcome contributes to learning.

## Add a connector

An installed connector is an ordinary Python function:

```python
def read(source: dict, root: Path):
    # Resolve an authorized source snapshot; emit canonical records.
    yield record
```

Register it in that package's `pyproject.toml`:

```toml
[project.entry-points."ai_data.connectors"]
my-source = "my_package.connector:read"
```

Invoke with `ai-data build recipe.json --output runs/custom-v1 --allow-plugins`. The connector validates its source options, emits stable IDs/revisions and declares groups and uses. MCP uses the built-in connectors.

Each source supplies a workspace-relative local `path` whose bytes are hashed. A remote connector can use that file as a pinned source descriptor and bind fetched bytes to declared revisions. Manifests record the plugin's distribution, version and entry point. Multi-input source snapshots and distributed preparation are extension points.

## Reuse targets

These are architectural reuse choices, **not implemented adapters**. Versions and capabilities were checked against the linked primary sources on 2026-11-17.

| Project / standard | Intended role | Boundary |
| --- | --- | --- |
| [Apache Arrow / Parquet](https://arrow.apache.org/docs/python/parquet/) | Columnar interchange and storage | Preserve common IDs and domain schema while changing physical representation. |
| [Apache Iceberg](https://iceberg.apache.org/spec/) | Table snapshots and schema/partition evolution when shared tables are needed | Reference a table snapshot; do not reimplement table transactions in the local manifest. |
| [OpenLineage](https://openlineage.io/docs/spec/object-model/) | Exchange dataset/job/run lineage | Map recipes and releases to existing lineage vocabulary; the local manifest is not an OpenLineage event. |
| [DataTrove](https://github.com/huggingface/datatrove) | Large text pipelines and deduplication | Import/export records and cluster IDs; keep composition/split choices explicit. |
| [NeMo Curator](https://github.com/NVIDIA-NeMo/Curator) | Scalable text, image, audio and video curation | Optional backend selected by workload and available hardware. |
| [Feast](https://docs.feast.dev/getting-started/concepts/point-in-time-joins) | Historical/online feature serving | Preserve entity identity and point-in-time selection; separately track when a value became available. |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x) | Agent tool transport | Pin the v1 API used here; upgrade through a tested interface change. |

Hugging Face datasets/Hub, object stores, SQL sources, search/knowledge systems, Ray/Spark, workflow engines, annotation systems and trainer-specific sinks are further integration targets. Choose each adapter from a concrete source or consumer workload.

## Deployment growth

The local library is the reference behavior. Shared deployment adds a transactional catalog and durable job state, object storage, identity-aware source access and asynchronous workers. Existing platform schedulers should execute jobs. The data service owns data/run/release state; it need not become a training scheduler or agent controller. Client requests should return job/release IDs and bounded summaries, not large datasets through MCP.
