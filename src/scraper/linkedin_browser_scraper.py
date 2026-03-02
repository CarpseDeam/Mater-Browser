"""Browser-based LinkedIn job scraper — only returns Easy Apply jobs."""
import logging
from typing import Optional
from playwright.sync_api import Page as PlaywrightPage
from src.scraper.jobspy_client import JobListing

logger = logging.getLogger(__name__)

SEARCH_URL_TEMPLATE = (
    "https://www.linkedin.com/jobs/search/?"
    "keywords={keywords}"
    "&f_AL=true"
    "&f_WT=2"
    "&sortBy=DD"
    "&start={start}"
)
MAX_PAGES = 3
JOBS_PER_PAGE = 25


class LinkedInBrowserScraper:
    def __init__(self, page: PlaywrightPage) -> None:
        self._page = page

    def search(self, keywords: str, max_results: int = 50) -> list[JobListing]:
        jobs: list[JobListing] = []
        seen_ids: set[str] = set()
        pages_to_scrape = min(MAX_PAGES, (max_results // JOBS_PER_PAGE) + 1)

        for page_num in range(pages_to_scrape):
            if len(jobs) >= max_results:
                break
            start = page_num * JOBS_PER_PAGE
            url = SEARCH_URL_TEMPLATE.format(keywords=keywords.replace(" ", "%20"), start=start)
            logger.info(f"Scraping LinkedIn search page {page_num + 1}: {keywords}")
            try:
                self._page.goto(url, wait_until="domcontentloaded", timeout=15000)
                self._page.wait_for_timeout(2000)
            except Exception as e:
                logger.warning(f"Navigation failed: {e}")
                break
            if "login" in self._page.url.lower() or "checkpoint" in self._page.url.lower():
                logger.error("LinkedIn session expired — redirected to login")
                break
            page_jobs = self._extract_jobs_from_page()
            for job in page_jobs:
                if job.id not in seen_ids and len(jobs) < max_results:
                    seen_ids.add(job.id)
                    jobs.append(job)
            logger.info(f"Page {page_num + 1}: {len(page_jobs)} jobs, total: {len(jobs)}")
            if len(page_jobs) < 5:
                break

        logger.info(f"Browser scrape: {len(jobs)} Easy Apply jobs for '{keywords}'")
        return jobs

    def _extract_jobs_from_page(self) -> list[JobListing]:
        try:
            raw_jobs = self._page.evaluate('''() => {
                const cards = document.querySelectorAll('[data-job-id]');
                const results = [];
                for (const card of cards) {
                    const hasEasyApply = card.querySelector('[data-test-icon="linkedin-bug-color-small"]') !== null
                        || (card.textContent || '').includes('Easy Apply');
                    if (!hasEasyApply) continue;
                    const jobId = card.getAttribute('data-job-id') || '';
                    if (!jobId) continue;
                    const titleEl = card.querySelector('a[class*="job-card"]') || card.querySelector('[class*="title"] a') || card.querySelector('a');
                    const title = (titleEl?.textContent || '').trim();
                    const subtitleEl = card.querySelector('[class*="subtitle"]') || card.querySelector('[class*="company"]');
                    const company = (subtitleEl?.textContent || '').trim().split('\\n')[0].trim();
                    const captionEl = card.querySelector('[class*="caption"]') || card.querySelector('[class*="location"]');
                    const location = (captionEl?.textContent || '').trim();
                    const linkEl = card.querySelector('a[href*="/jobs/view/"]');
                    const url = linkEl?.href || '';
                    if (title && jobId) results.push({ jobId, title, company, location, url });
                }
                return results;
            }''')
        except Exception as e:
            logger.warning(f"JS extraction failed: {e}")
            return []

        jobs: list[JobListing] = []
        for raw in raw_jobs:
            job_id = raw.get('jobId', '')
            url = raw.get('url', '')
            if not url and job_id:
                url = f"https://www.linkedin.com/jobs/view/{job_id}"
            elif url and '?' in url:
                url = url.split('?')[0]
            jobs.append(JobListing(
                id=f"li-{job_id}",
                title=raw.get('title', 'Unknown'),
                company=raw.get('company', 'Unknown'),
                location=raw.get('location', ''),
                url=url, description='', salary=None,
                date_posted=None, site='linkedin',
                is_remote=True, job_type=None,
            ))
        return jobs
