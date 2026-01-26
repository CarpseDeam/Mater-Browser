# Mater-Browser

Automated job application browser agent using Playwright and Claude AI.

## Architecture Overview

```
src/
├── agent/           # Application orchestration
│   ├── application.py   # Main ApplicationAgent - handles full apply flow
│   ├── claude.py        # Claude AI integration for form analysis
│   └── actions.py       # Action plan definitions
├── scraper/         # Job discovery
│   ├── scorer.py        # JobScorer - filters jobs by relevance
│   └── jobspy_client.py # Job listing data structures
├── browser/         # Browser abstraction
│   ├── page.py          # Page wrapper
│   └── tabs.py          # TabManager for multi-tab handling
├── extractor/       # DOM extraction
│   └── dom_service.py   # DomService for element extraction
└── executor/        # Action execution
    └── runner.py        # ActionRunner executes plans
```

## Key Components

### JobScorer (`src/scraper/scorer.py`)
Scores and filters job listings based on:
- Title keyword matching (40%)
- Skills match in description (40%)
- Remote preference (10%)
- Freshness/recency (10%)

**Exclusions:**
- `STACK_EXCLUSIONS` - Tech stacks not aligned with Python focus (.NET, Java, PHP, etc.)
- `ROLE_EXCLUSIONS` - Role types to exclude (junior, intern, sysadmin, QA, manager)
- Custom excluded keywords (principal, director, clearance required, etc.)

### ApplicationAgent (`src/agent/application.py`)
Orchestrates the complete job application flow:
1. Detects job source (LinkedIn, Indeed, Direct)
2. Finds and clicks Apply button
3. Handles external ATS redirects
4. Processes multi-page forms using Claude AI
5. Uploads resume or selects pre-uploaded resume
6. Detects submission completion

**Platform-specific handlers:**
- `_apply_linkedin()` - LinkedIn Easy Apply modal flow
- `_apply_external()` - Indeed/Direct with ATS redirect handling
- `_handle_indeed_resume_card()` - Indeed's resume selection page with already-selected detection
- `_click_indeed_continue()` - Indeed-specific Continue button with scroll support

## Changelog

### 2026-01-25 (update 2)
- Fixed `_handle_indeed_resume_card()` to detect already-selected resumes (checkmark indicator)
- Added `_click_indeed_continue()` for Indeed-specific Continue button patterns
- Now skips card click if user's PDF is already selected, preventing unwanted selection change
- Added scroll-to-find logic for Continue button below viewport

### 2026-01-25
- Added `ROLE_EXCLUSIONS` to scorer.py - excludes junior, intern, sysadmin, QA, and management roles
- Added `role_exclusions` parameter to JobScorer for customization
- Added `_handle_indeed_resume_card()` to application.py - clicks "Use your Indeed Resume" card
- Updated `_process_form_pages()` to try Indeed resume handler before DOM extraction
