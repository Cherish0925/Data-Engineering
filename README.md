# Data Engineering

**Data systems and research methods for AI: from source material to learning, retrieval, evaluation and feedback.**

[中文](README.zh-CN.md) · [Design](docs/design.zh-CN.md) · [Consumption](docs/consumption.md) · [Research](docs/research.md) · [Implementation status](docs/roadmap.md)

The central problem is choosing and delivering the data that improves a system under a compute budget. This project connects source snapshots, domain structure, transformations, mixtures and consumer feedback. Its scope covers pretraining and post-training, multimodal models, agents, retrieval and memory, conventional ML, robotics and scientific experiments.

The core is independent of a model provider, training framework or cloud. Qiushi Engine and RSI workflows are consumers alongside other AI systems. [Public workloads from OpenAI, Google DeepMind, Anthropic and DeepSeek](docs/frontier-workloads.md) motivate the architecture and its next experiments.

## Working data path

The v0.2 core supports two complementary operations. **Build** prepares a source release with explicit partitions and lineage. **Compose** selects from pinned releases to materialize a budgeted consumption stream, then delivers that stream through a checkpointable reader.

| Operation | Working capability |
| --- | --- |
| Prepare a release | Canonical JSONL and Gym imports, exact duplicate handling, parent/group relationships, deterministic splits, declared-use selection and record-level decisions. |
| Compose a distribution | Weighted source selection, deterministic source ordering, record or supplied-token budgets, explicit source exhaustion behavior and indexed JSONL shards. |
| Consume a mixture | Rank/world-size partitioning, optional equal-length ranks, direct indexed reads and reader state tied to the mixture and rank configuration. |
| Reuse experience | Import observations, actions, task splits, verification and rollout metadata from Verifiable Agent Gym as versioned trajectory records. |
| Work through an agent | Python, CLI and MCP operations over the same core, plus connector entry points and an operating Skill. |

Python 3.11 or newer; the core uses the standard library.

```sh
git clone https://github.com/Cherish0925/Data-Engineering.git
cd Data-Engineering
python -m pip install -e .
python examples/compose_training.py --output runs/training-example
ai-data verify-mixture runs/training-example/mixture
```

This example builds text and code source releases, pins their identities, composes 1,000 record draws at 3:1 source weights and resumes one of four reader ranks. The generated recipe can be edited and composed into a new output:

```sh
ai-data compose runs/training-example/mixture.recipe.json --output runs/mixture-v2
ai-data verify-mixture runs/mixture-v2
```

Use `python -m ai_data` wherever the `ai-data` entry point is unavailable. On systems without `python`, use `python3` or `py -3.11`.

## Source preparation and consumption

```sh
ai-data profile examples/records.jsonl
ai-data build examples/local.recipe.json --output runs/source-v1
ai-data verify runs/source-v1
ai-data inspect runs/source-v1
```

A release contains partition files, lineage, processing decisions and a content-derived manifest. Grouping happens before filtering and duplicate removal, so known copies and derivatives retain their partition relationship. Payloads keep domain structure: a preference pair, a sensor stream and a table do not have to become chat messages. [Data contracts](docs/contracts.md) define the record and release formats.

```python
from ai_data import MixtureReader

with MixtureReader("runs/training-example/mixture", rank=1, world_size=4) as reader:
    sample = next(reader)
    record = sample["record"]
    checkpoint = reader.state_dict()

with MixtureReader("runs/training-example/mixture", rank=1, world_size=4) as reader:
    reader.load_state_dict(checkpoint)
    next_sample = next(reader)
```

Mixtures select an explicit partition from each source. Token budgets use counts supplied by a named field in the records; the consumer defines the tokenizer, encoding and loss masks. [Consumption semantics](docs/consumption.md) cover recipes, exhaustion, rank assignment and restart. [The composition measurement script](examples/measure_composition.py) measures construction and reading separately from source preparation.

## Task data and feedback

[Verifiable Agent Gym](https://github.com/Cherish0925/Verifiable-Agent-Gym) turns task records into executable environments and records attempts by an external policy. Its SQL task packs can read Data Engineering releases. Its grouped rollout export returns task, policy, attempt, observation/action and outcome information to this project through the `gym-jsonl` connector.

```sh
ai-data build examples/gym.recipe.json --output runs/gym-trajectories
ai-data verify runs/gym-trajectories
```

For an actual run, point the recipe at an `agent-gym export` or `agent-gym export-rollouts` file and record its source revision. Gym executes interactions and evaluates results; Data Engineering constructs distributions and data products; the external trainer performs model inference and optimization. This separates data policy, environment feedback and learning measurements while keeping their identities connected.

With both repositories installed as sibling checkouts, run the complete task-to-experience path:

```sh
python examples/experience_cycle.py --gym-tasks ../Verifiable-Agent-Gym/examples/sql-workload/tasks.jsonl --output runs/experience-cycle
```

It builds a SQL task release, collects eight grouped attempts with passing and failing submissions, imports the trajectories, composes three shards and checks two reader ranks and exact restart.

## Research and extension

The research agenda is organized around decisions that can change capability: source allocation, synthetic candidate selection, task difficulty, experience reuse, multimodal alignment and feedback freshness. Each experiment relates an explicit data change to a consumer outcome and a budget. See [research methods](docs/research.md) and [frontier workload evidence](docs/frontier-workloads.md).

Install agent access with:

```sh
python -m pip install -e ".[mcp]"
ai-data connect --root . --output data-engineering.local.json
```

Import the configuration into a compatible MCP host. Tools expose profiling, release construction/inspection, composition and verification. The [operating Skill](skills/data-engineering/SKILL.md) and [integration guide](docs/integrations.md) describe agent and connector use.

The current implementation runs locally. Source preparation holds records in memory; mixture construction and reading use disk indexes and shards. Near-duplicate curation, model-specific tokenization/packing, multimodal decoding, remote workers and trainer integrations are the next workload-specific implementations. The examples exercise data flow with authored records and scripted policies; downstream learning results require an actual consumer experiment. [The roadmap](docs/roadmap.md) identifies these next steps.

```sh
python -m pip install -e ".[mcp,test]"
python -m unittest discover -s tests -v
python -m pip wheel . --no-deps --wheel-dir dist
```

Implementation is in `src/ai_data/`, executable recipes in `examples/`, and methods in `docs/`. Read [AGENTS.md](AGENTS.md) before contributing.
