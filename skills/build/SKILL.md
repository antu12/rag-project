---
name: build
description: Read a saved Markdown spec from the workspace specs directory and implement exactly what it describes. Use when the user invokes /build or $build, asks to build from a spec, references specs/name.md, or wants implementation constrained to documented requirements with a final requirement coverage list.
---

# Build

## Purpose

Use this skill to implement a feature or app from an existing spec file. The spec is the source of truth.

## Core Rules

- Read the relevant file in `specs/` before making implementation changes.
- Build exactly what the spec describes.
- Do not add features, screens, settings, integrations, states, copy, data fields, tests, or behavior that are not required or clearly implied by the spec.
- Do not refactor unrelated code, rename unrelated symbols, reformat unrelated files, or make opportunistic cleanup changes.
- Do not invent requirements to fill gaps. If a missing detail blocks implementation, ask one focused question before editing.
- If a missing detail does not block implementation, make the smallest reasonable assumption, record it in the final response, and keep the implementation easy to adjust.
- Preserve existing project conventions, architecture, styling, dependencies, and test patterns unless the spec explicitly requires a change.
- Keep changes scoped to files needed to satisfy the spec.

## Spec Selection

If the user names a spec, read that file from `specs/`. Accept references such as:

- `/build portfolio-tracker`
- `/build specs/portfolio-tracker.md`
- `Use $build for invite-flow`

If the user does not name a spec:

1. List available files in `specs/`.
2. If there is exactly one spec, use it.
3. If there are multiple specs, ask which one to build.
4. If there are no specs, tell the user to create one with `/spec` first.

Do not proceed without a spec file.

## Build Workflow

1. Read the full spec.
2. Extract a requirement checklist from the spec before editing:
   - Objective
   - Requirements
   - Constraints
   - Edge Cases
   - Definition of Done
3. Inspect only the project files needed to understand where the implementation belongs.
4. Implement the smallest cohesive change set that satisfies the checklist.
5. Add or update tests only when the spec calls for them, the repository has a relevant existing test pattern, or the changed behavior would be risky without them.
6. Run the most relevant verification commands available in the project, such as focused tests, type checks, lint checks, or build checks.
7. Compare the final changes against the requirement checklist.
8. In the final response, list which spec requirements were covered and note any requirements not covered or assumptions made.

## Handling Ambiguity

Ask before building when:

- The named spec file cannot be found.
- Multiple specs could match the user request.
- A requirement conflicts with existing code or another requirement.
- The spec omits a detail that materially changes the implementation approach.
- The spec's definition of done cannot be verified with available project tooling.

Proceed with a stated assumption when:

- The ambiguity is minor.
- The assumption follows existing project patterns.
- The implementation can be changed later without broad rework.

## Final Response Format

Keep the final response concise and include:

- The spec file used.
- A summary of the implementation.
- Verification performed, including commands run and whether they passed.
- A requirement coverage list mapping each major spec requirement to the completed work.
- Any assumptions, skipped items, or uncovered requirements.

Do not claim a requirement is covered unless the implementation or verification actually supports it.
