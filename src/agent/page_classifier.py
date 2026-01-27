"""Similo-inspired page classifier for apply button detection."""
import logging
import random
from enum import Enum
from typing import Optional

from playwright.sync_api import Locator, Page as PlaywrightPage

from .dom_extractor import DomExtractor, ElementCandidate
from .visibility_helpers import scroll_element_into_view, verify_element_visible

logger = logging.getLogger(__name__)


class PageType(Enum):
    EASY_APPLY = "easy_apply"
    EXTERNAL_LINK = "external"
    ALREADY_APPLIED = "applied"
    CLOSED = "closed"
    LOGIN_REQUIRED = "login"
    PAYMENT_DANGER = "payment_danger"
    ACCOUNT_CREATION = "account_creation"
    UNKNOWN = "unknown"


ALREADY_APPLIED_PHRASES = ["already applied", "you applied", "you have applied", "application submitted", "previously applied", "application on file"]
CLOSED_PHRASES = ["no longer accepting", "position filled", "position has been filled", "job has been filled", "no longer available", "this job is closed", "job is no longer", "posting has expired", "job expired", "job closed"]
PAYMENT_URL_PATTERNS = ["premium", "upgrade", "subscribe", "pricing", "checkout", "payment", "billing", "purchase", "cart", "order", "plans"]
SAFE_URL_PATTERNS = ["smartapply.indeed.com", "indeed.com/applystart", "linkedin.com/jobs"]
PAYMENT_CONTENT_PHRASES = ["enter payment", "credit card", "debit card", "billing information", "purchase now", "buy now", "upgrade to premium", "start free trial", "subscription", "per month", "/month", "/year", "indeed premium", "linkedin premium", "recruiter lite"]
PAYMENT_BUTTON_WORDS = ["buy", "purchase", "upgrade", "premium", "subscribe", "checkout", "pay now", "start trial", "get premium", "unlock", "pro version", "pricing"]
ACCOUNT_CREATION_URL_PATTERNS = ["register", "signup", "sign-up", "sign_up", "create-account", "create_account", "createaccount", "join", "registration", "new-account", "new_account", "newuser", "new-user"]
ACCOUNT_CREATION_CONTENT_PHRASES = ["create an account", "create your account", "create account", "sign up for", "register for", "join now", "join for free", "create password", "confirm password", "retype password", "already have an account", "have an account? sign in", "create your profile", "set up your account"]
NEGATIVE_TEXT_SIGNALS = ["save", "later", "dismiss", "close", "cancel", "not now"]
EXTERNAL_ARIA_PHRASES = ["on company website", "company site", "external site"]

LINKEDIN_EASY_APPLY_SELECTORS = [
    'button[data-control-name="jobdetails_topcard_inapply"]',
    'button.jobs-apply-button',
    'button[aria-label*="Easy Apply"]',
    'button.jobs-apply-button--top-card',
    '[data-testid="jobs-apply-button"]',
]


class PageClassifier:
    """Similo-inspired classifier for job application pages."""

    def __init__(self, page: PlaywrightPage) -> None:
        self._page = page
        self._dom_extractor = DomExtractor(page)
        self._candidates: Optional[list[ElementCandidate]] = None

    def classify(self) -> PageType:
        if self._is_payment_page():
            return PageType.PAYMENT_DANGER
        if self._is_account_creation_page():
            return PageType.ACCOUNT_CREATION
        try:
            content_lower = self._page.content().lower()[:5000]
        except Exception:
            content_lower = ""
        if any(p in content_lower for p in ALREADY_APPLIED_PHRASES):
            return PageType.ALREADY_APPLIED
        if any(p in content_lower for p in CLOSED_PHRASES):
            return PageType.CLOSED
        if self._check_login_required():
            return PageType.LOGIN_REQUIRED
        candidate = self.find_apply_button()
        return self._classify_apply_button(candidate) if candidate else PageType.UNKNOWN

    def _classify_apply_button(self, candidate: ElementCandidate) -> PageType:
        text_lower = candidate.text.lower()
        aria_lower = (candidate.aria_label or "").lower()
        role_lower = (candidate.role or "").lower()

        if "easy" in text_lower or "easy" in aria_lower:
            return PageType.EASY_APPLY

        is_external = (
            any(phrase in aria_lower for phrase in EXTERNAL_ARIA_PHRASES) or
            (candidate.tag == "button" and role_lower == "link") or
            (candidate.tag == "a" and candidate.href) or
            "apply on " in text_lower
        )
        return PageType.EXTERNAL_LINK if is_external else PageType.EASY_APPLY

    def find_apply_button(self, refresh: bool = False) -> Optional[ElementCandidate]:
        direct_match = self._try_linkedin_direct()
        if direct_match:
            return direct_match

        if self._candidates is None or refresh:
            raw_candidates = self._dom_extractor.extract_candidates()
            for c in raw_candidates:
                c.score = self._score_candidate(c)
            self._candidates = sorted(raw_candidates, key=lambda x: x.score, reverse=True)
        for candidate in self._candidates:
            if candidate.is_visible and candidate.score > 0:
                return candidate
        return None

    def _try_linkedin_direct(self) -> Optional[ElementCandidate]:
        for selector in LINKEDIN_EASY_APPLY_SELECTORS:
            try:
                locator = self._page.locator(selector).first
                if locator.is_visible(timeout=500):
                    text = locator.text_content() or ""
                    aria_label = locator.get_attribute("aria-label")
                    data_testid = locator.get_attribute("data-testid")
                    logger.debug(f"LinkedIn direct selector matched: {selector}")
                    return ElementCandidate(
                        selector=selector,
                        tag="button",
                        text=text.strip(),
                        role="button",
                        aria_label=aria_label,
                        href=None,
                        data_testid=data_testid,
                        is_visible=True,
                        score=10.0,
                    )
            except Exception:
                continue
        return None

    def click_apply_button(self, timeout: int = 8000) -> bool:
        candidate = self.find_apply_button() or self.find_apply_button(refresh=True)
        if not candidate:
            logger.warning("PageClassifier: No apply button candidate found")
            return False
        logger.info(f"PageClassifier: Clicking '{candidate.text}' (score={candidate.score:.2f})")
        self.dismiss_overlays()
        if self._try_click_candidate(candidate, timeout):
            self._page.wait_for_timeout(500)
            self.dismiss_overlays()
            return True
        self._page.wait_for_timeout(500)
        self.dismiss_overlays()
        candidate = self.find_apply_button(refresh=True)
        return self._try_click_candidate(candidate, timeout) if candidate else False

    def _try_click_candidate(self, candidate: ElementCandidate, timeout: int) -> bool:
        locator = self._page.locator(candidate.selector).first
        scroll_element_into_view(self._page, locator)
        verify_element_visible(self._page, locator)
        self._page.wait_for_timeout(random.randint(200, 500))
        return self._attempt_click_sequence(locator, timeout)

    def _score_candidate(self, candidate: ElementCandidate) -> float:
        score = 0.0
        text_lower = candidate.text.lower()
        if candidate.role == "button":
            score += 1.5
        elif candidate.role == "link":
            score += 1.2
        elif candidate.tag == "button":
            score += 1.4
        elif candidate.tag == "a":
            score += 1.0
        if "easy apply" in text_lower:
            score += 2.0
        elif "apply now" in text_lower:
            score += 1.8
        elif "apply on company" in text_lower or "apply on " in text_lower:
            score += 1.4
        elif "apply" in text_lower:
            score += 1.5
        if candidate.aria_label:
            aria_lower = candidate.aria_label.lower()
            score += 1.8 if "easy apply" in aria_lower else (1.2 if "apply" in aria_lower else 0)
        if candidate.data_testid:
            testid_lower = candidate.data_testid.lower()
            if "easyapply" in testid_lower or "easy-apply" in testid_lower:
                score += 1.5
            elif "apply" in testid_lower:
                score += 1.0
        if any(neg in text_lower for neg in NEGATIVE_TEXT_SIGNALS):
            score -= 2.0
        aria_lower = (candidate.aria_label or "").lower()
        if any(word in text_lower or word in aria_lower for word in PAYMENT_BUTTON_WORDS):
            score -= 10.0
        if not candidate.is_visible:
            score -= 3.0
        return score

    def dismiss_overlays(self) -> None:
        try:
            self._page.evaluate(self._get_overlay_removal_js())
        except Exception:
            pass

    def _get_overlay_removal_js(self) -> str:
        return '''() => {
            document.querySelector('.msg-overlay-list-bubble')?.remove();
            document.querySelectorAll('[class*="cookie"], [class*="consent"]').forEach(el => el.offsetParent && el.remove());
            document.querySelectorAll('[role="dialog"], [role="alertdialog"]').forEach(d => {
                const text = (d.textContent || '').toLowerCase();
                if (!text.includes('easy apply') && !text.includes('application') && d.offsetParent) d.remove();
            });
            document.querySelectorAll('.artdeco-toast-item, .notification-badge').forEach(n => n.remove());
            document.querySelectorAll('[class*="z-modal"][class*="bg-opacity"], [class*="bg-black"][class*="bg-opacity-50"]').forEach(el => {
                if (el.classList.contains('fixed') && el.offsetParent) el.remove();
            });
            document.querySelectorAll('[style*="pointer-events"]').forEach(el => {
                if (getComputedStyle(el).pointerEvents === 'none') return;
                const style = getComputedStyle(el);
                if (style.position === 'fixed' && parseInt(style.zIndex || 0) > 100) {
                    if (!el.querySelector('form, input, button[type="submit"]')) {
                        el.remove();
                    }
                }
            });
        }'''

    def _attempt_click_sequence(self, locator: Locator, timeout: int) -> bool:
        for attempt in self._click_attempts(locator, timeout):
            try:
                if attempt():
                    return True
            except Exception:
                pass
        return False

    def _click_attempts(self, locator: Locator, timeout: int):
        yield lambda: (locator.click(timeout=timeout), True)[1]
        yield lambda: (box := locator.bounding_box(timeout=1000)) and (locator.click(timeout=timeout, position={"x": box['width'] / 2, "y": box['height'] / 2}), True)[1]
        yield lambda: (locator.evaluate("el => el.click()"), True)[1]
        yield lambda: (locator.click(timeout=timeout, force=True), True)[1]

    def _check_login_required(self) -> bool:
        try: return self._page.locator('input[type="password"]').first.is_visible(timeout=1000)
        except Exception: return False

    def _is_payment_page(self) -> bool:
        url_lower = self._page.url.lower()
        if any(safe in url_lower for safe in SAFE_URL_PATTERNS):
            return False
        if any(p in url_lower for p in PAYMENT_URL_PATTERNS):
            logger.warning(f"PAYMENT URL DETECTED: {self._page.url}")
            return True
        try:
            phrases_js = "[" + ", ".join(f'"{p}"' for p in PAYMENT_CONTENT_PHRASES) + "]"
            if self._page.evaluate(f'() => {phrases_js}.some(p => document.body.innerText.toLowerCase().includes(p))'):
                logger.warning(f"PAYMENT CONTENT DETECTED: {self._page.url}")
                return True
        except Exception:
            pass
        return False

    def _is_account_creation_page(self) -> bool:
        url_lower = self._page.url.lower()
        if any(p in url_lower for p in ACCOUNT_CREATION_URL_PATTERNS):
            logger.warning(f"ACCOUNT CREATION URL DETECTED: {self._page.url}")
            return True
        try:
            phrases_js = "[" + ", ".join(f'"{p}"' for p in ACCOUNT_CREATION_CONTENT_PHRASES) + "]"
            if self._page.evaluate(f'() => {phrases_js}.some(p => document.body.innerText.toLowerCase().includes(p)) || !!document.querySelector(\'input[name*="confirm"], input[name*="retype"], input[placeholder*="confirm"], input[placeholder*="retype"]\')'):
                logger.warning(f"ACCOUNT CREATION CONTENT DETECTED: {self._page.url}")
                return True
        except Exception:
            pass
        return False
