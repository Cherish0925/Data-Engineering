# Data Engineering

**A research and engineering environment for the full AI data lifecycle.**

[中文](README.zh-CN.md) · [System design / 总体设计](docs/design.zh-CN.md) · [Data contracts](docs/contracts.md) · [Integrations](docs/integrations.md) · [Research](docs/research.md) · [Roadmap](docs/roadmap.md)

Data determines what an AI system can learn, retrieve, evaluate, remember, and improve. This project brings those uses into one coherent engineering environment: sources and observations become versioned data products, their consumers return outcomes, and those outcomes inform the next collection or processing decision.

The scope includes conventional machine learning, foundation models, multimodal generation, agents, robotics, and scientific systems. Qiushi Engine, RSI workflows, and model training platforms are consumers and collaborators. The core has no dependency on any of them, on a model provider, or on a particular cloud.

## Scope

| Workload | Data responsibilities |
| --- | --- |
| Pretraining and continual pretraining | Acquisition, extraction, deduplication, corpus composition, tokenization and packing recipes, dataset versions. |
| Supervised and preference learning | Demonstrations, labels, conversations, tool calls, preferences, reward and critic targets, annotation uncertainty. |
| Reinforcement learning and agents | Task distributions, environment/verifier references, trajectories, rewards, failures, replay and curricula. |
| Evaluation | Benchmark construction, protected splits, contamination analysis, frozen versions, result attribution. |
| Retrieval and memory | Documents, chunks, embeddings, indexes, context selection, permissions, freshness and corrections. |
| Tabular, graph and time-series ML | Entities, labels, features, temporal joins, graph relationships, online/offline feature consistency. |
| Multimodal and embodied AI | Image, audio, video, spatial data, synchronized sensor/action streams, coordinate systems and episodes. |
| Scientific and experimental AI | Measurements, units, uncertainty, calibration, simulation conditions, interventions and experimental lineage. |
| Continuous operation | Feedback, drift, active collection, synthetic generation, retention and withdrawal of affected products. |

This is the **design scope**. The current implementation is a local reference core, described below. Domain decoders, distributed execution, and managed services are staged in the roadmap.

## One core, several ways to use it

The shared contract retains a typed payload and its source, revision, declared uses, ancestry and split group. A recipe turns these records into a release with partition files, record-level decisions, lineage and a content-derived manifest. Domain extensions keep their own payload schemas; an image, a preference pair and a physical measurement are not forced into chat messages.

Python, CLI and MCP call the same implementation. A bundled [agent Skill](skills/data-engineering/SKILL.md) explains how to work with it. Trusted Python connector packages extend acquisition through an entry point. These are distinct functions: prompts guide work, connectors access sources, tools perform operations, and the runtime produces results.

## Run the reference pipeline

Python 3.11 or newer. The core uses the standard library and requires no GPU or model key.

```sh
git clone https://github.com/Cherish0925/Data-Engineering.git
cd Data-Engineering
python -m pip install -e .
ai-data profile examples/records.jsonl
ai-data build examples/local.recipe.json --output runs/local-v1
ai-data verify runs/local-v1
ai-data inspect runs/local-v1
```

Use `python3` on systems without `python`, or `py -3.11` on Windows. `python -m ai_data` is equivalent to `ai-data`.

The seven authored fixture records produce five retained records: one duplicate is removed and one record lacks the requested use. Output contains three train records, one validation record and one test record. The media example is an external reference, not a downloaded image or a working image decoder.

The builder groups related records **before** removing duplicates or filtering by use. A held-out document therefore keeps its known copies and derivatives out of the training partition. Conflicting fixed partitions stop the build. Exact content matching does not establish semantic independence; domain-specific grouping and near-duplicate analysis remain necessary for real datasets.

```python
from ai_data import build, verify_release

manifest = build("examples/local.recipe.json", "runs/python-v1")
print(manifest["release_id"])
print(verify_release("runs/python-v1"))
```

Each output directory is a new release. Existing releases are never overwritten. `use="train"` selects records whose declarations permit this use; a trainer must still consume **only `train.jsonl`**, not all partitions. Files are canonical records, not automatically tokenized trainer inputs.

## Agent access

```sh
python -m pip install -e ".[mcp]"
ai-data connect --root examples --output data-engineering.local.json
```

Import the generated configuration into a compatible MCP host. It uses the installed Python interpreter and an explicit workspace. The five tools are `data_capabilities`, `data_profile`, `data_build`, `data_inspect`, and `data_verify`. For the fixture workspace, call `data_build(recipe="local.recipe.json", output="runs/mcp-v1")`.

The server uses the official MCP Python SDK v1 interface (`mcp>=1.29,<2`). It is a local stdio server; remote hosting and host-specific marketplace packages are not included. MCP source and output paths are confined to the configured workspace, and dynamic connector plugins are disabled through this interface.

## Verifiable Agent Gym

The built-in `gym-jsonl` connector reads the [Verifiable Agent Gym](https://github.com/Cherish0925/Verifiable-Agent-Gym) export-v1 format. It preserves task splits, observations/actions, verifier results, and null rewards for unscored failures.

```sh
ai-data build examples/gym.recipe.json --output runs/gym-v1
ai-data verify runs/gym-v1
```

These fixtures test the format. To use a real run, export it with `agent-gym export`, supply the export path, source revision and declared uses in a recipe, and build a separate release. Gym executes tasks and verifies submissions; Data Engineering prepares task/trajectory products. RL optimization remains with the trainer. No Gym installation is required to import an existing export.

## Implementation and development

Working now: canonical JSONL and Gym readers; contract validation; source hashes; exact duplicate handling; transitive grouping through content, group IDs and parents; deterministic splits; declared-use filtering; release manifests; local integrity checking; Python/CLI/MCP; trusted connector entry points.

The reference builder holds records in memory. It does not yet implement near-duplicate search, tokenization, distributed processing, database/Hub connectors, external artifact fetching, online indexes, or automatic data optimization. The [roadmap](docs/roadmap.md) distinguishes these from implemented features.

```sh
python -m pip install -e ".[mcp,test]"
python -m unittest discover -s tests -v
python -m pip wheel . --no-deps --wheel-dir dist
```

Code lives in `src/ai_data/`; design and research in `docs/`; executable recipes in `examples/`; agent guidance in `skills/`; behavioral tests in `tests/`. Start with [AGENTS.md](AGENTS.md) when contributing. Prefer a working data transformation, interoperable adapter, or useful research result over additional framework layers.
