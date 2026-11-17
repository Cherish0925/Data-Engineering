# Implementation status and next work

Status at the initial v0.1 implementation. The full scope is in [the design](design.zh-CN.md); this page records working capabilities and the next concrete development steps.

Local validation on 2026-11-17: 19 tests passed on Linux/Python 3.12, including a real MCP stdio handshake and tool calls; a wheel built successfully. Six scripted reference episodes from Gym commit `47f86d6df665388bf6d6627b8f8c403c8e5d2567` were executed, exported, imported and verified as a data release. This checks integration, not model ability. CI is configured for Linux, Windows and macOS with Python 3.11/3.13; configuration alone is not a completed run on those platforms.

| Area | Implemented | Next meaningful increment |
| --- | --- | --- |
| Contracts and releases | Generic envelope, strict JSON, recipe validation, byte hashes, core fingerprint, lineage and immutable-by-convention release directories. | Versioned domain profiles and artifact byte verification, followed by consumer bindings and revocation state. |
| Acquisition | Local canonical JSONL and Gym export-v1 readers; trusted installed connector extension point. | A real external source with pinned revisions, pagination/checkpoints and explicit failure recovery. |
| Data preparation | Exact matching; preserve provenance/annotation differences; declared-use selection. | Near-duplicate clusters through an established backend, then domain-specific transformations. |
| Splitting | Transitive grouping before filtering, parent links, fixed holdouts and deterministic component assignment. | Persistent cross-release group assignments, temporal and template-family splits. |
| Consumption | Canonical partition files for generic consumers. | One trainer export with correct loss masks/format, one retrieval product with citations and freshness, one factual trajectory/replay product. |
| Agent access | Python, CLI, local MCP and operating Skill. | Durable asynchronous jobs and host-specific plugin packaging when an actual host is selected. |
| Scale and modalities | Heterogeneous JSON payloads and artifact references; in-memory local builder. | Arrow/Parquet and object shards, one multimodal decoder/alignment path, measured throughput and restart behavior. |
| Continuous data | Versioned local snapshots. | Incremental ingestion, event/available times, source corrections, deletion propagation, drift and refresh policies. |
| Research | Defined questions and reusable release mechanism. | Downstream experiments on mixture/selection, synthetic task generalization and feedback reuse. |

## Implementation order

1. Connect real consumers to the reference core. Retain the original data-generating assumptions and deliver usable exports, rather than expanding field names without a consumer.
2. Solve the first scale bottleneck using an existing backend. Measure memory, bytes, throughput and cost. Add remote execution only where it materially helps.
3. Support durable incremental use: consistent source snapshots, retry semantics, stable partitions, corrections and affected-consumer tracking.
4. Develop data methods using downstream experiments, then expose successful methods as versioned recipes and tools.

All domains belong in the project scope from the outset; they do not need separate placeholder packages. Each adapter should provide a working example, preserve domain meaning and state what is actually exercised. No performance, generality or model-quality result is claimed by the authored fixtures.
