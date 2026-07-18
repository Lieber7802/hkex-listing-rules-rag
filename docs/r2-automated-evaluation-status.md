# R2 Automated-Only Evaluation Status

## Release Scope

`v1.1-r2-automated` is the frozen R2 dataset release used for
the automated system run. It contains 130 cases, the frozen source snapshot,
the passed R1 isolation report, independent judge records, automated audit
records, automated validation records, and an explicit quality-caveat file.

## Review Mode

This release is marked `review_mode=automated_only` and
`human_review_status=not_performed`. Its 130 cases were checked by structured
static validation and automated agents. No human expert reviewed or approved a
case. Automated assessment records retain the reviewer identifier, model,
prompt hash, protocol, evidence dimensions, and status.

## Reporting Constraint

Results from this release support a reproducible automated engineering
comparison of B3, A1, A2, and A3. They must not be described as
human-expert-reviewed or as a human-validated confirmatory study. The
post-run acceptance audit also found that the deterministic GAC scorer is not a
valid confirmatory implementation of the R2 metric, that this release is not
strictly unseen after prior v1.1 runs, and that a single DeepSeek run does not
meet the registered three-repeat requirement. A later human-reviewed unseen
release may supersede this one without changing its preserved artifacts.

## Quality Caveats

The release contains 13 cases with judge-recorded minor annotation caveats,
such as truncated answer-point text, generic tool-answer wording, or a missing
explicit comparison relation. Every applicable structured judge score still
meets the preregistered threshold of 4. The caveats are retained in
`quality_caveats.json` and must be disclosed with any reported result rather
than being hidden or silently redefined after inspection.

## Reproducibility

The release manifest hashes every included artifact. Evaluation run manifests
also record the release-manifest hash, code revision, index hash, embedding
model, LLM model, and execution configuration.
