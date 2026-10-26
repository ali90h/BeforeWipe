# BeforeWipe

## Foundational vision

BeforeWipe is an open-source project intended to help developers understand whether their important local work can survive a machine wipe or replacement. Its purpose is to turn uncertainty into an informed readiness decision before work becomes inaccessible.

## The problem

A developer’s working context extends beyond published repositories. Local-only code context, Claude Code and Codex sessions, unpublished Git changes, and other critical work may remain on a single machine. A backup’s existence alone does not establish that this work is included, usable, or recoverable.

## Intended user and desired outcome

BeforeWipe is for developers preparing to wipe, replace, or retire a development machine. It should provide readiness awareness, clearly identify work at risk, and help developers verify recoverability. It should distinguish evidence of recovery from assumptions and unknowns, so users can decide what still needs attention without receiving false reassurance.

## Differentiation hypothesis

The hypothesis is that a developer-focused view of local work and its recoverability could make pre-wipe decisions more useful than a general backup checklist alone. This is a proposition to test with developers, not a claim of proven novelty or superiority.

## Privacy and safety principles

- Local-first: keep assessment and user data on the developer’s machine by default.
- Read-only risk assessment by default: do not modify, move, delete, or publish work as part of assessing it.
- Never access or collect secrets. Never transmit user data without explicit, informed consent.
- Make uncertainty and assessment limits visible; do not equate detection, backup presence, or an unchecked assumption with verified recoverability.
- Keep the developer in control of access and any action affecting their work.

## Measuring usefulness

Test the idea with actual developers preparing for machine wipes or replacements. Evaluate whether they discover important at-risk work they had overlooked, understand what is recoverable and what remains uncertain, and can demonstrate recovery of selected important work. Gather feedback on missed risks, false alarms, effort required, and whether the assessment helped them make a better readiness decision. Use observed results to refine the product; do not assume usefulness in advance.

## Ownership of technical decisions

The coding agent owns all architecture, technology stack, internal design, implementation phases, and technical decisions. This document defines only the product’s foundational intent, desired outcomes, and boundaries. The agent should choose how to realize them based on evidence and the project’s needs.
