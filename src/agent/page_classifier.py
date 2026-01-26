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


ALREADY_APPLIED_PHRASES: list[str] = [
    "already applied", "you applied", "you have applied",
    "application submitted", "previously applied", "application on file",
]
CLOSED_PHRASES: list[str] = [
    "no longer accepting", "position filled", "position has been filled",
    "job has been filled", "no longer available", "this job is closed",
    "job is no longer", "posting has expired", "job expired", "job closed",
]
PAYMENT_URL_PATTERNS: list[str] = [
    "premium", "upgrade", "subscribe", "pricing", "checkout", "payment", "billing", "purchase", "cart", "order", "plans",
]
PAYMENT_CONTENT_PHRASES: list[str] = [
    "enter payment", "credit card", "debit card", "billing information", "purchase now", "buy now",
    "upgrade to premium", "start free trial", "subscription", "per month", "/month", "/year",
    "indeed premium", "linkedin premium", "recruiter lite",
]
PAYMENT_BUTTON_WORDS: list[str] = [
    "buy", "purchase", "upgrade", "premium", "subscribe", "checkout", "pay now", "start trial", "get premium", "unlock", "pro version", "pricing",
]
ACCOUNT_CREATION_URL_PATTERNS: list[str] = [
    "register", "signup", "sign-up", "sign_up", "create-account", "create_account", "createaccount",
    "join", "registration", "new-account", "new_account", "newuser", "new-user",
]
ACCOUNT_CREATION_CONTENT_PHRASES: list[str] = [
    "create an account", "create your account", "create account", "sign up for", "register for",
    "join now", "join for free", "create password", "confirm password", "retype password",
    "already have an account", "have an account? sign in", "create your profile", "set up your account",
]
NEGATIVE_TEXT_SIGNALS: list[str] = ["save", "later", "dismiss", "close", "cancel", "not now"]


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
        if any(phrase in content_lower for phrase in ALREADY_APPLIED_PHRASES):
            return PageType.ALREADY_APPLIED
        if any(phrase in content_lower for phrase in CLOSED_PHRASES):
            return PageType.CLOSED
        if self._check_login_required():
            return PageType.LOGIN_REQUIRED
        candidate = self.find_apply_button()
        if candidate:
            combined = candidate.text.lower() + " " + (candidate.aria_label or "").lower()
            if "easy" in combined:
                return PageType.EASY_APPLY
            if candidate.tag == "a" and candidate.href:
                return PageType.EXTERNAL_LINK
            return PageType.EASY_APPLY
        return PageType.UNKNOWN

    def find_apply_button(self, refresh: bool = False) -> Optional[ElementCandidate]:
        if self._candidates is None or refresh:
            raw_candidates = self._dom_extractor.extract_candidates()
            for c in raw_candidates:
                c.score = self._score_candidate(c)
            self._candidates = sorted(raw_candidates, key=lambda x: x.score, reverse=True)
        for candidate in self._candidates:
            if candidate.is_visible and candidate.score > 0:
                return candidate
        return None

    def click_apply_button(self, timeout: int = 8000) -> bool:
        candidate = self.find_apply_button() or self.find_apply_button(refresh=True)
        if not candidate:
            logger.warning("PageClassifier: No apply button candidate found")
            return False
        logger.info(f"PageClassifier: Clicking '{candidate.text}' (score={candidate.score:.2f})")
        self._dismiss_overlays()
        locator = self._page.locator(candidate.selector).first
        scroll_element_into_view(self._page, locator)
        verify_element_visible(self._page, locator)
        self._page.wait_for_timeout(random.randint(200, 500))
        if self._attempt_click_sequence(locator, timeout):
            return True
        candidate = self.find_apply_button(refresh=True)
        if not candidate:
            return False
        locator = self._page.locator(candidate.selector).first
        scroll_element_into_view(self._page, locator)
        verify_element_visible(self._page, locator)
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

    def _dismiss_overlays(self) -> None:
        try:
            self._page.evaluate('''() => {
                document.querySelector('.msg-overlay-list-bubble')?.remove();
                document.querySelectorAll('[class*="cookie"], [class*="consent"]').forEach(el => el.offsetParent && el.remove());
                document.querySelectorAll('[role="dialog"], [role="alertdialog"]').forEach(d => {
                    const text = (d.textContent || '').toLowerCase();
                    if (!text.includes('easy apply') && !text.includes('application') && d.offsetParent) d.remove();
                });
                document.querySelectorAll('.artdeco-toast-item, .notification-badge').forEach(n => n.remove());
            }''')
        except Exception:
            pass

    def _attempt_click_sequence(self, locator: Locator, timeout: int) -> bool:
        try:
            locator.click(timeout=timeout)
            return True
        except Exception:
            pass
        try:
            box = locator.bounding_box(timeout=1000)
            if box:
                locator.click(timeout=timeout, position={"x": box['width'] / 2, "y": box['height'] / 2})
                return True
        except Exception:
            pass
        try:
            locator.evaluate("el => el.click()")
            return True
        except Exception:
            pass
        try:
            locator.click(timeout=timeout, force=True)
            return True
        except Exception:
            pass
        return False

    def _check_login_required(self) -> bool:
        try:
            return self._page.locator('input[type="password"]').first.is_visible(timeout=1000)
        except Exception:
            return False

    def _is_payment_page(self) -> bool:
        url_lower = self._page.url.lower()
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
            if self._page.evaluate(f'''() => {{
                if ({phrases_js}.some(p => document.body.innerText.toLowerCase().includes(p))) return true;
                return !!document.querySelector('input[name*="confirm"], input[name*="retype"], input[placeholder*="confirm"], input[placeholder*="retype"]');
            }}'''):
                logger.warning(f"ACCOUNT CREATION CONTENT DETECTED: {self._page.url}")
                return True
        except Exception:
            pass
        return False
