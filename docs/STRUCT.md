# Mater-Browser

**Language:** Python
**Stack:** Pydantic, Pytest, Playwright

## Purpose

Automated job search and application browser. Orchestrates job discovery via JobSpy, scoring/filtering based on profile match, and application submission through browser automation.

## Architecture Overview

```
src/
├── automation/
│   ├── runner.py          # AutomationRunner - main loop orchestrating search/apply cycles
│   └── search_generator.py # Generates search terms from profile
├── scraper/
│   ├── jobspy_client.py   # JobSpyClient - fetches job listings
│   └── scorer.py          # JobScorer - filters/scores jobs against profile
├── queue/
│   └── manager.py         # JobQueue - persistence for pending/applied/failed jobs
├── profile/
│   └── manager.py         # User profile management
└── core/
    └── config.py          # Settings/configuration
```

## Key Components

- **AutomationRunner** (`src/automation/runner.py`): Background thread orchestrating search → score → queue → apply cycles. Communicates with main thread via request/result queues for Playwright operations.
- **JobScorer** (`src/scraper/scorer.py`): Filters jobs by exclusion rules (stack, role, keywords) and scores remaining jobs (0.0-1.0) based on title match, skills, remote preference, and freshness.
- **JobQueue** (`src/queue/manager.py`): Persistent queue tracking job states (pending, applied, failed, skipped).

## Changelog

- **2026-01-25**: Added job re-validation before apply
  - `JobScorer.passes_filter(job)` - single-job validation check
  - `JobScorer.get_exclusion_reason(job)` - returns exclusion reason for logging
  - `AutomationRunner._apply_to_job` - re-validates jobs before sending ApplyRequest, marks stale entries as skipped

## Stats

- files: 1832
- dirs: 426
- lines: 14635
