---
name: data-engineering
description: Prepare, compose and consume versioned AI data with the Data Engineering repository. Use for source preparation, task and trajectory data, weighted training mixtures, indexed shards, resumable readers, or data research across training, retrieval, evaluation and scientific workloads.
---

# Data Engineering

Start from the consumer, intended use, source revision and independence unit. Read the repository's `docs/contracts.md` before changing a recipe or adapter; read `docs/design.zh-CN.md` for the full scope. Resolve these paths from the repository root, two directories above this file. Keep this skill with the repository when installing it in an agent host.

Use the installed `ai-data` command or `python -m ai_data`; call the equivalent MCP tools when available. Query `data_capabilities` before assuming an adapter exists.

1. Inspect a sample and its generating process. Preserve modality structure, units, timestamps, uncertainty and source references.
2. Normalize to the record envelope. Choose globally scoped IDs and groups. Link source/derived records with `parents`; retain fixed evaluation splits. Keep observations, annotations, synthetic outputs and unscored failures distinguishable.
3. Profile canonical JSONL with `ai-data profile`. For Gym exports, use the `gym-jsonl` reader in a recipe rather than profiling the raw export as canonical records.
4. Build a new source release with `ai-data build RECIPE --output OUTPUT`. CLI source paths default to the recipe directory; MCP source paths use its configured workspace.
5. Inspect counts, decisions and lineage, then run `ai-data verify OUTPUT`. If related records have conflicting fixed splits, resolve the actual data relationship instead of deleting split labels to make the build pass.
6. For a training mixture, pin source release IDs and partitions in a composition recipe, choose source weights, a record/token budget and exhaustion behavior, then run `ai-data compose RECIPE --output OUTPUT` and `ai-data verify-mixture OUTPUT`.
7. Use `MixtureReader` for rank-partitioned consumption. Save its state with the corresponding model/optimizer checkpoint. Read `docs/consumption.md` for supplied token counts, fixed worker topology and equal-rank tail handling.

Preserve previous releases when changing data, labels, processing or recipes. Extend modality processing and consumer formatting through the appropriate existing backend. For task-driven learning, run `examples/experience_cycle.py` with Verifiable Agent Gym installed: task release → grouped episodes → trajectory release → training mixture → reader.

For extensions, read `docs/integrations.md`. Keep SDK, CLI and MCP on the shared core. For research, use `docs/research.md` to turn a proposed data decision into a downstream experiment at a comparable budget. Report data composition, systems throughput and learning effects separately.
