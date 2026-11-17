# Research agenda

The question is how data choices change useful capability under a resource budget. A dataset-level score is a measurement of one property, not a universal ordering of datasets.

## Questions that lead to experiments

| Question | Intervention | What would change our decision? |
| --- | --- | --- |
| Which additional data has marginal value? | Compare coverage-aware selection, random additions and current selection at matched training budgets. | A reproducible gain on the intended task distribution, including costly or rare failures. |
| What mixture and curriculum work? | Change source proportions, difficulty schedules or replay allocation while fixing the consumer and total budget. | Better learning efficiency or final capability, with the affected domains identified. |
| When does synthetic data add information? | Vary generation conditions, teacher diversity and verification independently; group shared ancestors. | Benefits that persist beyond template duplicates and held-out generator families. |
| Which tasks teach transferable behavior? | Vary task/environment families and reward construction; hold out mechanisms, instances or compositions as appropriate. | Transfer to different tasks or environments, not merely new seeds of the same template. |
| Which structure must multimodal data preserve? | Compare sampling/alignment/representation choices under the same consumer architecture. | Changes attributable to temporal, spatial or causal structure, measured on relevant outcomes. |
| How should deployed feedback become learning data? | Compare feedback selection and refresh policies with fixed temporal windows and explicit consumer versions. | Improved adaptation without using information unavailable at the time or losing earlier capability. |

These are research directions, not results already obtained by this repository.

## Experimental unit and attribution

Start with the consumer, task distribution, data-generating process and independence unit. Count independent documents, entities, task families, scenes or experiments alongside rows/tokens. A hundred paraphrases of one source are not a hundred independent observations.

Record the manipulated data decision, the release, the consumer version, the compute budget and the downstream outcome. Use suitable baselines and repetitions when variation matters. Compare data policies at matched resource budgets, or explicitly measure the resulting cost/performance tradeoff. Processing throughput and memory matter when they determine which policy is affordable.

When both data and consumer change, hold one fixed or use the necessary crossed comparisons to identify the cause. Model/harness comparisons follow the same principle. Split by time, ancestry or mechanism when those variables define the desired generalization; a random row split may answer a different question.

## What to preserve

Preserve raw observations, transformations, generation conditions, rejected examples and reasons when they are informative, annotation disagreements, verifier versions and consumer feedback. Preserve failure categories: wrong prediction, invalid action, missing evidence, environment failure, timeout and cancellation can require different remedies.

For experiments and robotics, distinguish observation from intervention, simulation from measurement, and estimated labels from reference values. Units, uncertainty, synchronization and coordinate transformations affect meaning; they are part of the data method.

## First useful research artifacts

Use small, executable studies that can be scaled: a corpus-mixture comparison, a synthetic-task family with a meaningful holdout, or a trajectory-to-training transformation with measured downstream effect. Store code, recipes and compact results in Git; reference versioned large data externally. A study should explain why a data decision helped or failed, and what another researcher can reuse.

The core currently supplies release construction and interfaces. Automated mixture optimization, active collection, task synthesis, data valuation and continual-learning policies remain research work. A new research direction should produce a method or an informative experiment before introducing another management layer.
