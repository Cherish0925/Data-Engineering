# Implementation status and next work

v0.2 connects source releases to budgeted consumption and task data to grouped experience. The [design](design.zh-CN.md) defines the full AI scope; [frontier workloads](frontier-workloads.md) explain the public technical requirements behind it.

## Working capabilities

| Area | Implemented in v0.2 | Next useful increment |
| --- | --- | --- |
| Source releases | Typed record envelope, JSONL/Gym connectors, source hashes, exact duplicate handling, lineage, declared-use selection and content-derived manifests. | An external source with pinned snapshots and an established curation backend for a corpus larger than memory. |
| Independence and partitions | Transitive content/group/parent relationships before filtering, fixed holdouts and deterministic assignment. | Persistent cross-release assignments, near-duplicate clusters and time or task-mechanism splits. |
| Composition | Pinned source releases and partitions, weighted record draws, record/supplied-token budgets, source exhaustion policies and indexed shards. | Tokenizer-aware packing and consumer measurements of exposure, padding and useful training throughput. |
| Consumption | `MixtureReader` with rank assignment, optional equal-length ranks and state restoration for the same release and rank configuration. | A framework adapter that coordinates reader state with the model/optimizer checkpoint and loss construction. |
| Executable task data | Companion Gym reads canonical task releases; SQL packs supply schema/query tools and result verification. | A larger externally sourced task set with diverse databases, meaningful holdouts and measured execution cost. |
| Feedback | Gym export-v1 import preserves task partitions and full trajectory payloads, including grouped rollout and policy metadata. | A consumer experiment comparing candidate selection, fresh experience and replay. |
| Agent access | Shared Python/CLI/MCP operations for build, inspect, composition and verification; connector extension points and operating guidance. | Durable jobs or additional service adapters when a workload requires them. |
| Other modalities and continuous use | Domain payloads and artifact references share the record/release system. | One complete multimodal alignment path and one incremental retrieval or feature product. |

Source preparation is currently an in-memory local operation. Composition scans source partitions and uses disk indexes and output shards; readers access assigned records directly. Domain decoders, model-specific tokenization, remote execution and automatic data-policy optimization remain separate implementation work.

## Next research and engineering increments

1. **Close a real consumer loop.** Connect a training framework to `MixtureReader` and Gym rollouts. Preserve encoding, loss masks, policy statistics and checkpoint position. The result is a reproducible training or evaluation run with a measured downstream outcome.
2. **Expand beyond authored fixtures.** Ingest a pinned external corpus and a larger task dataset. Compare source allocation or candidate selection while fixing the consumer and budget; report coverage and held-out behavior as well as aggregate scores.
3. **Remove the measured scale bottleneck.** Use the composition measurement script to separate source preparation, materialization and rank reading. Add an established columnar/curation backend or remote workers where memory, I/O or execution time limits the experiment.
4. **Preserve structure across modalities and updates.** Deliver one consumer-ready multimodal or scientific product with alignment and units, then incremental versions with event/availability times and stable identities.
5. **Turn useful data policies into reusable methods.** Promote mixture, curriculum, synthetic selection and feedback strategies only after a downstream experiment establishes when they help and what they cost.

The steps can proceed in parallel where interfaces are independent. Scope is shared across AI domains; each addition should complete a usable source-to-consumer path.

## Reproduce the current paths

[The composition example](../examples/compose_training.py) builds sources, composes a mixture and restores a rank reader. [The measurement script](../examples/measure_composition.py) reports input/output volume, shards, composition time, peak RSS where available and rank read times; source preparation and measurement run in separate processes. [Consumption documentation](consumption.md) defines their semantics.

The companion Gym's [training interface](https://github.com/Cherish0925/Verifiable-Agent-Gym/blob/main/docs/training.md) exercises task suites and batched interaction; its SQL task pack exercises Data Engineering releases as executable task sources. Unit tests cover these contracts and failure cases. The authored examples establish functioning data paths; learning gains and production-scale performance must be measured with the corresponding workload.

The [experience-cycle example](../examples/experience_cycle.py) joins both repositories: a task release produces eight grouped SQL attempts, a trajectory release and three consumption shards, with two-rank reading and exact cursor restoration.
