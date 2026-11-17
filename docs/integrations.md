# Integrations

All current front ends use `ai_data.pipeline`. The environment can run independently; integrating with a consumer should not import that consumer into the core.

## Implemented interfaces

| Interface | Current support |
| --- | --- |
| Python | `build(recipe_path, output, root=None, allow_plugins=False)`, `profile(path)`, `inspect_release(path)`, `verify_release(path)`. |
| CLI | `build`, `profile`, `inspect`, `verify`, `schema`, `connect`, `serve`; JSON stdout, errors on stderr with exit code 2. |
| MCP | Five local stdio tools, official Python SDK v1, one explicit filesystem workspace, no dynamic connector code. |
| Skill | `skills/data-engineering/SKILL.md`, repository-scoped operating guidance for compatible agent hosts. It is not automatically installed in any account. |
| Connector plugin | Installed Python entry points under `ai_data.connectors`, explicitly enabled by SDK/CLI. No marketplace package or compatibility claim for every host. |
| Canonical JSONL | Native reader for record schema `1.0`. |
| Verifiable Agent Gym | Native reader for export schema `1`; task splits and factual trajectories are retained. |

## Gym handoff

Read against [Gym commit 47f86d6](https://github.com/Cherish0925/Verifiable-Agent-Gym/tree/47f86d6df665388bf6d6627b8f8c403c8e5d2567), especially [`export.py`](https://github.com/Cherish0925/Verifiable-Agent-Gym/blob/47f86d6df665388bf6d6627b8f8c403c8e5d2567/src/agent_gym/export.py). This adapter consumes an exported file; it does not launch Gym.

```sh
agent-gym export runs/my-agent --output workspace/gym-export.jsonl --include-unscored
```

Check the installed Gym CLI for its supported flags if using a different version. Create a recipe in `workspace` using connector `gym-jsonl`, the export's relative path, a source URI/revision and `allowed_uses`. The runnable example is `examples/gym.recipe.json`.

The adapter preserves the whole exported payload. Records are grouped by task family, version, original split and seed, keeping difficulty variants, agents and attempts together. Scored `passed`/`failed` records must carry a finite reward in [0,1]; unscored records retain null rewards. Success does not synthesize missing reasoning, policy probabilities or a preference comparison. A training adapter must explicitly decide how to use failures, timeouts and scored attempts.

## Add a trusted connector

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

Invoke with `ai-data build recipe.json --output runs/custom-v1 --allow-plugins`. The connector must validate its own source options, emit stable IDs/revisions and declare meaningful groups and uses. Treat record text as data. An installed plugin has ordinary process privileges; the entry point is not a sandbox.

In v0.1 every source still supplies a workspace-relative local `path` whose bytes are hashed. A remote connector may use that file as a pinned source descriptor, but the connector must bind fetched remote bytes to declared revisions. The core does not verify remote immutability, checkpoints or hidden dependencies; multi-input/streaming source manifests are planned. Plugin distribution name/version and entry point are recorded, but the installed plugin's full source and environment are not yet hashed.

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

Hugging Face datasets/Hub, object stores, SQL sources, search/knowledge systems, Ray/Spark, workflow engines, annotation systems and trainer-specific sinks are further integration targets. Add them when a concrete source or consumer requires them; do not advertise them as connected because a name appears in a table.

## Deployment growth

The local library is the reference behavior. Shared deployment adds a transactional catalog and durable job state, object storage, identity-aware source access and asynchronous workers. Existing platform schedulers should execute jobs. The data service owns data/run/release state; it need not become a training scheduler or agent controller. Client requests should return job/release IDs and bounded summaries, not large datasets through MCP.
