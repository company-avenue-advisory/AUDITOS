# Engineering Documentation

Execution-level documents — how the accepted doctrine in [`../rfc/`](../rfc/README.md) gets turned into shipped, maintained software. These are living documents (revised as the team learns), unlike the RFCs, which are accepted and superseded rather than edited in place.

## What's here, and why

- **[ENGINEERING_EXECUTION_BLUEPRINT.md](ENGINEERING_EXECUTION_BLUEPRINT.md)** — converts RFC-005 into Programs, Epics, ADR decisions, repo structure, roadmap, and a self-critical Red Team review. Read this to understand *what we're building, in what order, and why something was deliberately deferred or deleted.*
- **[ENGINEERING_PRINCIPLES.md](ENGINEERING_PRINCIPLES.md)** — 50 permanent working rules (deterministic-before-AI, build-moats-buy-commodities, prefer deletion over complexity, etc.). Read this to understand *how we make small decisions day to day without re-deriving them from the RFCs each time.* Hand this to a new engineer on day one.
- **[PROJECT_BOOTSTRAP.md](PROJECT_BOOTSTRAP.md)** — the first 100 concrete, ordered engineering tasks. Read this to understand *what to actually do this week.*

## Reading order

New to the project: RFCs (`../rfc/`) → `ENGINEERING_PRINCIPLES.md` → `ENGINEERING_EXECUTION_BLUEPRINT.md` → `PROJECT_BOOTSTRAP.md`.
Picking up work day to day: `PROJECT_BOOTSTRAP.md` for the next task → `ENGINEERING_PRINCIPLES.md` when a decision needs a rule → `ENGINEERING_EXECUTION_BLUEPRINT.md` when a task needs its owning Program/Epic/ADR for context.

## Engineering workflow

```
RFC            (../rfc/ — accepted doctrine: why and what)
  ↓
ADR            (../adr/ — a specific, scoped technical decision, with a review trigger)
  ↓
Bootstrap      (PROJECT_BOOTSTRAP.md — the ordered task that implements the decision)
  ↓
Implementation (review existing code → reuse/refactor → write code → write tests)
  ↓
Evaluation     (../evaluation/ — regression suite + golden-set/professional-grading pass)
  ↓
Release        (commit, scoped to one task; deploy off main)
```

A change that can't be traced up this chain to an RFC or an ADR is either genuinely new doctrine (write the RFC/ADR first) or scope creep (per `ENGINEERING_PRINCIPLES.md` #48 and the Blueprint's Red Team Review — cut it).
