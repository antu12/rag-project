---
name: spec
description: Interview the user to define a feature, application, product idea, or implementation request before any building begins. Use when the user invokes /spec or $spec, asks to create a spec, wants requirements clarified, wants a feature/app planned through questions, or wants a detailed specification saved under the specs directory.
---

# Spec

## Purpose

Use this skill to turn an unclear feature or app idea into a concrete written specification. The output is a saved Markdown spec, not implemented code.

## Core Rules

- Do not start building, coding, scaffolding, designing screens, installing packages, or modifying product files beyond creating the final spec document.
- Ask exactly one focused question at a time.
- Keep each question easy to answer and tied to the most important missing information.
- Continue interviewing until the objective, must-have requirements, constraints, edge cases, and definition of done are clear enough to write an actionable spec.
- Prefer concrete answers over broad brainstorming. When the user is vague, ask for a specific choice, example, workflow, user type, limit, or acceptance criterion.
- If the user explicitly says to make reasonable assumptions, state the assumptions in the spec instead of continuing to ask about every detail.
- Save the finished spec to `specs/<name>.md` in the current workspace. Create `specs/` if it does not exist.

## Interview Workflow

1. Start by asking what feature or app the user wants to specify, unless they already provided it.
2. Ask one follow-up question at a time, selecting the highest-impact missing detail.
3. Cover these areas before writing:
   - Objective: the problem, target user, and intended outcome.
   - Scope: what is in scope and what is explicitly out of scope.
   - Must-have requirements: functional behavior, data, workflows, states, permissions, integrations, and UX expectations.
   - Constraints: platform, stack, existing codebase boundaries, timeline, performance, compliance, security, budget, dependencies, or operational limits.
   - Edge cases: invalid input, empty/loading/error states, permissions failures, network/API failures, concurrency, retries, partial completion, data migration, and accessibility needs where relevant.
   - Definition of done: concrete acceptance criteria, tests or checks, deliverables, and what the user should be able to verify.
4. When enough information is gathered, say that you have enough to write the spec and proceed without asking for confirmation unless a major ambiguity remains.
5. Write the spec and save it.

## Question Selection

Ask the next question from the area with the largest remaining uncertainty. Good question shapes include:

- "Who is the primary user, and what are they trying to accomplish?"
- "What is the first workflow that must work end to end?"
- "What inputs and outputs should this feature handle?"
- "What should happen when there is no data, bad input, or a failed dependency?"
- "Are there any existing files, APIs, design patterns, or tech constraints this must fit?"
- "What would make you say this is done and ready to use?"

Do not ask multi-part questionnaires. If a topic naturally has several parts, choose the single part that matters most next.

## Spec File

Choose a short, filesystem-safe `<name>` from the feature or app name:

- Use lowercase letters, digits, and hyphens.
- Keep it descriptive, for example `portfolio-tracker.md` or `invite-flow.md`.
- If the name would collide with an existing spec, append a short suffix such as `-v2` or ask the user if overwriting would be risky.

The spec must include these sections:

```markdown
# <Title>

## Objective

## Requirements

## Constraints

## Edge Cases

## Definition of Done
```

Add extra sections only when they make the spec clearer, such as `Out of Scope`, `User Flows`, `Data Model`, `Open Questions`, or `Assumptions`.

## Writing Standards

- Be specific enough that another engineer or agent can build from the spec without re-interviewing the user.
- Use imperative, testable language for requirements.
- Separate must-haves from assumptions or future ideas.
- Include open questions only for non-blocking ambiguity. If a question blocks the spec, ask it before writing.
- Keep the final response brief: report the saved path and summarize the objective and done criteria.
