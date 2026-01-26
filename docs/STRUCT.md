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
Scores and filters job listings for Python Backend/Platform Engineer roles (4+ years experience).

**Scoring (0.0-1.0):**
- Title keyword matching (40%) - python, backend, platform, data engineer, etc.
- Skills + positive signals match (40%) - profile skills AND tech signals (fastapi, postgres, aws, etc.)
- Remote preference (10%)
- Freshness/recency (10%)

**Exclusions:**
- `STACK_EXCLUSIONS` - Incompatible tech stacks (.NET, Java, PHP, Ruby, Go, Mobile, etc.)
- `ROLE_EXCLUSIONS` - Non-target roles (junior, full stack, devops, QA, management, over-senior)
- `excluded_keywords` - Clearance requirements, 10+ years experience, location restrictions

**Positive Signals:**
- `POSITIVE_SIGNALS` - Boost score for Python ecosystem (fastapi, django), data tools (postgres, snowflake), cloud (aws, docker)

**Minimum score:** 0.5 (raised from 0.4 for stricter filtering)

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

### 2026-01-25 (update 3)
- Complete overhaul of JobScorer for targeted Python Backend/Platform Engineer filtering
- Expanded `STACK_EXCLUSIONS` to 30+ patterns (.NET, Java, PHP, Ruby, Go, Mobile, Enterprise, Data Science)
- Expanded `ROLE_EXCLUSIONS` to 35+ patterns (junior, full stack, devops, QA, management, security, over-senior)
- Added `POSITIVE_SIGNALS` list - 25+ patterns for Python ecosystem, data tools, cloud infrastructure
- Updated `excluded_keywords` defaults - clearance, location restrictions, incompatible tech requirements
- Updated `title_keywords` defaults - backend, platform, data engineer, api engineer, systems engineer
- Score now combines profile skills + positive signals (need 3+ matches for full 40%)
- Raised `min_score` from 0.4 to 0.5 for stricter filtering
- Added `positive_signals` parameter to JobScorer for customization

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
