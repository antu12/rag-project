---
name: review
description: Compare the current workspace build against a saved Markdown spec in the specs directory and audit every requirement. Use when the user invokes /review or $review, asks to review against a spec, references specs/name.md for validation, or wants gaps, bugs, missing pieces, and specific fixes handed back for /build.
---

# Review

## Purpose

Use this skill to decide whether the current build fully satisfies an existing spec. The spec is the source of truth, and the review only passes when every requirement is fully met.

## Core Rules

- Read the relevant file in `specs/` before reviewing implementation.
- Review requirement by requirement, including objective, explicit requirements, constraints, edge cases, and definition of done.
- Name the exact spec item that each gap, bug, missing piece, or unverifiable behavior fails.
- Do not fix code during review unless the user explicitly asks for fixes in the same request.
- Do not pass the build when any requirement is missing, partially implemented, buggy, unverified, or contradicted by implementation.
- Do not invent new requirements or judge against preferences that are not in the spec.
- Do not ignore constraints or edge cases because the main happy path works.
- If anything fails, write specific fixes that `/build` can apply.

## Spec Selection

If the user names a spec, read that file from `specs/`. Accept references such as:

- `/review portfolio-tracker`
- `/review specs/portfolio-tracker.md`
- `Use $review for invite-flow`

If the user does not name a spec:

1. List available files in `specs/`.
2. If there is exactly one spec, use it.
3. If there are multiple specs, ask which one to review.
4. If there are no specs, tell the user to create one with `/spec` first.

Do not proceed without a spec file.

## Review Workflow

1. Read the full spec.
2. Extract a checklist of every reviewable item from:
   - Objective
   - Requirements
   - Constraints
   - Edge Cases
   - Definition of Done
   - Any additional spec sections that contain requirements, such as User Flows, Data Model, Accessibility, or Assumptions
3. Inspect the current implementation and tests needed to evaluate the checklist.
4. Run relevant verification commands when available, such as tests, type checks, lint checks, build checks, or targeted manual checks.
5. Compare each spec item against actual behavior and verification evidence.
6. Classify each item as:
   - `Pass`: fully implemented and verified enough for the spec.
   - `Fail`: missing, incorrect, incomplete, contradicted, or not implemented.
   - `Unverified`: likely implemented but not confirmed by code, tests, or runnable checks.
7. Treat `Fail` and `Unverified` as not passing the build.
8. Write specific fixes for every `Fail` or `Unverified` item so `/build` can address them.

## Failure Reporting

For each issue, include:

- Exact spec item: quote or precisely name the requirement being failed.
- Finding: what is missing, wrong, buggy, or unverifiable.
- Evidence: file path, behavior, command output summary, or inspection result when available.
- Required fix: the concrete change `/build` should make.

Keep findings ordered by severity and then by spec order.

## Pass Criteria

Only pass the build when:

- Every spec requirement is implemented.
- Every edge case in the spec is handled.
- Every constraint in the spec is respected.
- The definition of done is satisfied.
- Relevant verification has passed, or the spec does not require runnable verification and code inspection is sufficient.

If verification could not be run, do not mark affected items as passed unless inspection conclusively proves them.

## Final Response Format

Start with one of:

- `Review failed`
- `Review passed`

For a failed review, include:

- Spec file used.
- Verification performed.
- Requirement-by-requirement results.
- Specific fixes needed for `/build`.

For a passed review, include:

- Spec file used.
- Verification performed.
- Requirement-by-requirement pass list.
- Any residual risks that do not block the spec.

Do not soften a failed review with a general approval summary. The handoff to `/build` should be clear and actionable.
