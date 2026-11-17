# Data Engineering

Build the data systems and methods that improve AI capability and research throughput. Serve pretraining, post-training, agents, retrieval, multimodal and scientific workloads through a common core.

Start with the workload, consumer, data-generating process and compute budget. Read `docs/research.md` for the research questions, `docs/contracts.md` for release semantics, and `docs/integrations.md` for interfaces. Public technical motivations are collected in `docs/frontier-workloads.md`.

- Deliver a usable data operation or a result that changes a research decision. Prefer a small coherent implementation over another framework layer.
- Preserve domain structure, source versions, independent sample groups and observed feedback. Keep transformations explicit and reproducible.
- Measure composition, consumption and learning separately: bytes/records/tokens, throughput/memory/restart, then downstream capability at a comparable budget.
- Reuse established storage, curation, tokenization and execution systems. Keep Python, CLI and MCP on the same implementation.
- Keep large payloads outside Git; publish code, recipes, compact fixtures and reproducible measurements.
- Update both entry pages with working behavior. Describe limitations once at the relevant interface, with a concrete consequence.
- Use topic branches and pull requests. Preserve existing consumers and unrelated work.

Run `python -m unittest discover -s tests -v`. Exercise the data recipe and actual consumer path affected by a change. For interface changes, exercise the installed CLI or MCP transport as appropriate.
