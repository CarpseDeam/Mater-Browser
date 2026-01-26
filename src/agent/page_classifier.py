"""Similo-inspired page classifier for apply button detection."""
import logging
import random
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from playwright.sync_api import Locator, Page as PlaywrightPage

logger = logging.getLogger(__name__)


class PageType(Enum):
    """Classification of job application page type."""
    EASY_APPLY = "easy_apply"
    EXTERNAL_LINK = "external"
    ALREADY_APPLIED = "applied"
    CLOSED = "closed"
    LOGIN_REQUIRED = "login"
    PAYMENT_DANGER = "payment_danger"
    ACCOUNT_CREATION = "account_creation"
    UNKNOWN = "unknown"


@dataclass
class ElementCandidate:
    """Candidate element for apply button detection."""
    selector: str
    tag: str
    text: str
    role: Optional[str]
    aria_label: Optional[str]
    href: Optional[str]
    data_testid: Optional[str]
    is_visible: bool
    score: float = field(default=0.0)


ALREADY_APPLIED_PHRASES: list[str] = [
    "already applied",
    "you applied",
    "you have applied",
    "application submitted",
    "previously applied",
    "application on file",
]

CLOSED_PHRASES: list[str] = [
    "no longer accepting",
    "position filled",
    "position has been filled",
    "job has been filled",
    "no longer available",
    "this job is closed",
    "job is no longer",
    "posting has expired",
    "job expired",
    "job closed",
]

PAYMENT_URL_PATTERNS: list[str] = [
    "premium", "upgrade", "subscribe", "pricing",
    "checkout", "payment", "billing", "purchase",
    "cart", "order", "plans",
]

PAYMENT_CONTENT_PHRASES: list[str] = [
    "enter payment", "credit card", "debit card",
    "billing information", "purchase now", "buy now",
    "upgrade to premium", "start free trial",
    "subscription", "per month", "/month", "/year",
    "indeed premium", "linkedin premium", "recruiter lite",
]

PAYMENT_BUTTON_WORDS: list[str] = [
    "buy", "purchase", "upgrade", "premium", "subscribe",
    "checkout", "pay now", "start trial", "get premium",
    "unlock", "pro version", "pricing",
]

ACCOUNT_CREATION_URL_PATTERNS: list[str] = [
    "register", "signup", "sign-up", "sign_up", "create-account",
    "create_account", "createaccount", "join", "registration",
    "new-account", "new_account", "newuser", "new-user",
]

ACCOUNT_CREATION_CONTENT_PHRASES: list[str] = [
    "create an account", "create your account", "create account",
    "sign up for", "register for", "join now", "join for free",
    "create password", "confirm password", "retype password",
    "already have an account", "have an account? sign in",
    "create your profile", "set up your account",
]

NEGATIVE_TEXT_SIGNALS: list[str] = [
    "save",
    "later",
    "dismiss",
    "close",
    "cancel",
    "not now",
]


class PageClassifier:
    """
    Similo-inspired classifier for job application pages.

    Uses batch DOM extraction and weighted scoring to find the best
    apply button candidate on a page.
    """

    def __init__(self, page: PlaywrightPage) -> None:
        self._page = page
        self._candidates: Optional[list[ElementCandidate]] = None

    def classify(self) -> PageType:
        """
        Classify the current page type.

        Priority-ordered checks:
        1. Payment/purchase danger (ABORT)
        2. Already applied indicators
        3. Job closed indicators
        4. Login required (password field visible)
        5. Apply button analysis
        6. Unknown (default)
        """
        if self._is_payment_page():
            return PageType.PAYMENT_DANGER

        if self._is_account_creation_page():
            return PageType.ACCOUNT_CREATION

        try:
            content_lower = self._page.content().lower()[:5000]
        except Exception:
            content_lower = ""

        if any(phrase in content_lower for phrase in ALREADY_APPLIED_PHRASES):
            logger.debug("PageClassifier: ALREADY_APPLIED (phrase match)")
            return PageType.ALREADY_APPLIED

        if any(phrase in content_lower for phrase in CLOSED_PHRASES):
            logger.debug("PageClassifier: CLOSED (phrase match)")
            return PageType.CLOSED

        if self._check_login_required():
            logger.debug("PageClassifier: LOGIN_REQUIRED")
            return PageType.LOGIN_REQUIRED

        candidate = self.find_apply_button()
        if candidate:
            text_lower = candidate.text.lower()
            aria_lower = (candidate.aria_label or "").lower()
            combined = text_lower + " " + aria_lower

            if "easy" in combined:
                logger.debug("PageClassifier: EASY_APPLY (easy in text)")
                return PageType.EASY_APPLY

            if candidate.tag == "a" and candidate.href:
                logger.debug("PageClassifier: EXTERNAL_LINK (anchor with href)")
                return PageType.EXTERNAL_LINK

            logger.debug("PageClassifier: EASY_APPLY (generic apply button)")
            return PageType.EASY_APPLY

        logger.debug("PageClassifier: UNKNOWN")
        return PageType.UNKNOWN

    def find_apply_button(self, refresh: bool = False) -> Optional[ElementCandidate]:
        """
        Find the highest-scoring visible apply button candidate.

        Args:
            refresh: If True, forces a fresh DOM extraction.

        Returns:
            Best ElementCandidate if found, None otherwise.
        """
        if self._candidates is None or refresh:
            self._candidates = self._extract_candidates()

        for candidate in self._candidates:
            if candidate.is_visible and candidate.score > 0:
                return candidate

        return None

    def click_apply_button(self, timeout: int = 8000) -> bool:
        """
        Find and click the best apply button candidate.

        Args:
            timeout: Click timeout in milliseconds.

        Returns:
            True if clicked successfully, False otherwise.
        """
        candidate = self.find_apply_button()

        if not candidate:
            logger.debug("PageClassifier: No candidate found, refreshing DOM...")
            candidate = self.find_apply_button(refresh=True)

        if not candidate:
            logger.warning("PageClassifier: No apply button candidate found after refresh")
            return False

        logger.info(f"PageClassifier: Clicking '{candidate.text}' (score={candidate.score:.2f})")

        self._dismiss_overlays()

        locator = self._page.locator(candidate.selector).first

        if not self._scroll_element_into_view(locator):
            logger.warning("PageClassifier: Failed to bring element into view")

        if not self._verify_element_visible(locator):
            logger.warning("PageClassifier: Element not visible after scroll attempts")

        self._page.wait_for_timeout(random.randint(200, 500))

        if self._attempt_click_sequence(locator, timeout):
            return True

        logger.debug("PageClassifier: First click sequence failed, refreshing DOM...")
        candidate = self.find_apply_button(refresh=True)
        if not candidate:
            logger.error("PageClassifier: No candidate found after refresh")
            return False

        locator = self._page.locator(candidate.selector).first
        self._scroll_element_into_view(locator)
        self._verify_element_visible(locator)

        if self._attempt_click_sequence(locator, timeout):
            return True

        logger.error("PageClassifier: All click attempts failed")
        return False

    def _dismiss_overlays(self) -> None:
        """Remove overlays and modals that might intercept clicks."""
        try:
            self._page.evaluate('''() => {
                // Close LinkedIn messaging overlay
                const msgOverlay = document.querySelector('.msg-overlay-list-bubble');
                if (msgOverlay) msgOverlay.remove();

                // Close cookie banners
                const cookieBanners = document.querySelectorAll(
                    '[class*="cookie"], [class*="consent"], [id*="cookie"], [id*="consent"]'
                );
                cookieBanners.forEach(el => {
                    if (el.offsetParent !== null) el.remove();
                });

                // Close generic modal dialogs (excluding job application modals)
                const dialogs = document.querySelectorAll('[role="dialog"], [role="alertdialog"]');
                dialogs.forEach(d => {
                    const text = (d.textContent || '').toLowerCase();
                    const isApplyModal = text.includes('easy apply') || text.includes('application');
                    if (!isApplyModal && d.offsetParent !== null) {
                        d.remove();
                    }
                });

                // Close floating notifications
                const notifications = document.querySelectorAll(
                    '.artdeco-toast-item, .notification-badge, [class*="popup"]'
                );
                notifications.forEach(n => n.remove());
            }''')
            logger.debug("PageClassifier: Dismissed overlays")
        except Exception as e:
            logger.debug(f"PageClassifier: Overlay dismissal error - {e}")

    def _scroll_element_into_view(self, locator: Locator) -> bool:
        """Scroll page to bring element to viewport center, accounting for sticky headers."""
        try:
            box = locator.bounding_box(timeout=2000)
            if not box:
                locator.scroll_into_view_if_needed(timeout=2000)
                return True

            viewport = self._page.viewport_size
            if not viewport:
                locator.scroll_into_view_if_needed(timeout=2000)
                return True

            header_offset = self._get_sticky_header_height()
            usable_height = viewport['height'] - header_offset
            target_y = box['y'] - header_offset - (usable_height / 2) + (box['height'] / 2)

            self._page.evaluate(f"window.scrollTo({{top: {target_y}, behavior: 'smooth'}})")
            self._page.wait_for_timeout(500)
            return True
        except Exception as e:
            logger.debug(f"PageClassifier: Scroll error - {e}")
            return False

    def _get_sticky_header_height(self) -> int:
        """Detect sticky/fixed headers and return their height."""
        try:
            return self._page.evaluate('''() => {
                const headers = document.querySelectorAll('header, nav, [class*="header"], [class*="navbar"]');
                let maxHeight = 0;
                for (const el of headers) {
                    const style = getComputedStyle(el);
                    if (style.position === 'fixed' || style.position === 'sticky') {
                        const rect = el.getBoundingClientRect();
                        if (rect.top <= 10 && rect.height > maxHeight) {
                            maxHeight = rect.height;
                        }
                    }
                }
                return Math.ceil(maxHeight) || 60;
            }''')
        except Exception:
            return 60

    def _verify_element_visible(self, locator: Locator, max_attempts: int = 3) -> bool:
        """Verify element visibility with retry scrolling."""
        for attempt in range(max_attempts):
            try:
                if locator.is_visible(timeout=1000):
                    return True
                locator.scroll_into_view_if_needed(timeout=2000)
                self._page.wait_for_timeout(300)
            except Exception:
                pass
        return False

    def _check_click_intercepted(self, locator: Locator) -> bool:
        """Check if another element would intercept the click."""
        try:
            box = locator.bounding_box(timeout=1000)
            if not box:
                return True

            center_x = box['x'] + box['width'] / 2
            center_y = box['y'] + box['height'] / 2

            is_intercepted = self._page.evaluate(f'''() => {{
                const el = document.elementFromPoint({center_x}, {center_y});
                if (!el) return true;

                const target = document.querySelector('{locator.first._selector if hasattr(locator, "_selector") else ""}');
                if (!target) return false;

                return !target.contains(el) && !el.contains(target) && el !== target;
            }}''')

            if is_intercepted:
                logger.debug("PageClassifier: Click would be intercepted, dismissing overlays")
                self._dismiss_overlays()
                return True
            return False
        except Exception:
            return False

    def _attempt_click_sequence(self, locator: Locator, timeout: int) -> bool:
        """Execute click sequence with fallbacks."""
        self._check_click_intercepted(locator)

        # Attempt 1: Normal click
        try:
            locator.click(timeout=timeout)
            logger.debug("PageClassifier: Normal click succeeded")
            return True
        except Exception as e:
            logger.debug(f"PageClassifier: Normal click failed - {e}")

        # Attempt 2: Click at element center with position
        try:
            box = locator.bounding_box(timeout=1000)
            if box:
                locator.click(
                    timeout=timeout,
                    position={"x": box['width'] / 2, "y": box['height'] / 2}
                )
                logger.debug("PageClassifier: Position click succeeded")
                return True
        except Exception as e:
            logger.debug(f"PageClassifier: Position click failed - {e}")

        # Attempt 3: JavaScript click
        try:
            locator.evaluate("el => el.click()")
            logger.debug("PageClassifier: JS click succeeded")
            return True
        except Exception as e:
            logger.debug(f"PageClassifier: JS click failed - {e}")

        # Attempt 4: Force click (last resort)
        try:
            locator.click(timeout=timeout, force=True)
            logger.debug("PageClassifier: Force click succeeded")
            return True
        except Exception as e:
            logger.debug(f"PageClassifier: Force click failed - {e}")

        return False

    def _extract_candidates(self) -> list[ElementCandidate]:
        """
        Batch extract all potential apply button candidates.

        Uses a single evaluate call for efficiency.
        """
        raw_elements = self._page.evaluate('''() => {
            const candidates = document.querySelectorAll('button, a, [role="button"], [role="link"]');
            return Array.from(candidates).map((el, idx) => {
                const text = (el.textContent || '').trim().slice(0, 100);
                const ariaLabel = el.getAttribute('aria-label') || '';
                const testId = el.getAttribute('data-testid') || '';
                const searchText = (text + ' ' + ariaLabel + ' ' + testId).toLowerCase();

                if (!searchText.includes('apply')) {
                    return null;
                }

                const rect = el.getBoundingClientRect();
                return {
                    idx: idx,
                    tag: el.tagName.toLowerCase(),
                    text: text,
                    role: el.getAttribute('role'),
                    aria_label: ariaLabel || null,
                    href: el.getAttribute('href'),
                    data_testid: testId || null,
                    is_visible: el.offsetParent !== null && rect.width > 0 && rect.height > 0,
                };
            }).filter(e => e !== null);
        }''')

        candidates = []
        for raw in raw_elements:
            selector = self._build_selector(raw)
            candidate = ElementCandidate(
                selector=selector,
                tag=raw['tag'],
                text=raw['text'],
                role=raw.get('role'),
                aria_label=raw.get('aria_label'),
                href=raw.get('href'),
                data_testid=raw.get('data_testid'),
                is_visible=raw['is_visible'],
            )
            candidate.score = self._score_candidate(candidate)
            candidates.append(candidate)

        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def _build_selector(self, raw: dict) -> str:
        """Build a reliable CSS selector for a candidate element."""
        if raw.get('data_testid'):
            return f'[data-testid="{raw["data_testid"]}"]'

        if raw.get('aria_label'):
            escaped = raw['aria_label'].replace('"', '\\"')
            return f'{raw["tag"]}[aria-label="{escaped}"]'

        text = raw.get('text', '').strip()
        if text and len(text) < 50:
            escaped_text = text.replace('"', '\\"')
            return f'{raw["tag"]}:text-is("{escaped_text}")'

        base_query = 'button, a, [role="button"], [role="link"]'
        return f':is({base_query}) >> nth={raw["idx"]}'

    def _score_candidate(self, candidate: ElementCandidate) -> float:
        """
        Score a candidate using Similo-style weighted attributes.

        Higher scores indicate better apply button matches.
        """
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
            if "easy apply" in aria_lower:
                score += 1.8
            elif "apply" in aria_lower:
                score += 1.2

        if candidate.data_testid:
            testid_lower = candidate.data_testid.lower()
            if "easyapply" in testid_lower or "easy-apply" in testid_lower:
                score += 1.5
            elif "apply" in testid_lower:
                score += 1.0

        if any(neg in text_lower for neg in NEGATIVE_TEXT_SIGNALS):
            score -= 2.0

        aria_lower = (candidate.aria_label or "").lower()
        for word in PAYMENT_BUTTON_WORDS:
            if word in text_lower or word in aria_lower:
                score -= 10.0
                break

        if not candidate.is_visible:
            score -= 3.0

        return score

    def _check_login_required(self) -> bool:
        """Check if current page requires login."""
        try:
            password_field = self._page.locator('input[type="password"]').first
            return password_field.is_visible(timeout=1000)
        except Exception:
            return False

    def _is_payment_page(self) -> bool:
        """Detect payment/upgrade/purchase pages - ABORT if found."""
        url_lower = self._page.url.lower()
        if any(pattern in url_lower for pattern in PAYMENT_URL_PATTERNS):
            logger.warning(f"PAYMENT URL DETECTED: {self._page.url}")
            return True

        try:
            phrases_js = "[" + ", ".join(f'"{p}"' for p in PAYMENT_CONTENT_PHRASES) + "]"
            has_payment_content = self._page.evaluate(f"""
                () => {{
                    const text = document.body.innerText.toLowerCase();
                    const dangerPhrases = {phrases_js};
                    return dangerPhrases.some(phrase => text.includes(phrase));
                }}
            """)
            if has_payment_content:
                logger.warning(f"PAYMENT CONTENT DETECTED on page: {self._page.url}")
                return True
        except Exception as e:
            logger.debug(f"Payment content check error: {e}")

        return False

    def _is_account_creation_page(self) -> bool:
        """Detect account creation/registration pages - ABORT if found."""
        url_lower = self._page.url.lower()
        if any(pattern in url_lower for pattern in ACCOUNT_CREATION_URL_PATTERNS):
            logger.warning(f"ACCOUNT CREATION URL DETECTED: {self._page.url}")
            return True

        try:
            phrases_js = "[" + ", ".join(f'"{p}"' for p in ACCOUNT_CREATION_CONTENT_PHRASES) + "]"
            has_creation_content = self._page.evaluate(f"""
                () => {{
                    const text = document.body.innerText.toLowerCase();
                    const phrases = {phrases_js};
                    if (phrases.some(p => text.includes(p))) return true;

                    // Check for password confirmation field (strong signal)
                    const confirmPwd = document.querySelector(
                        'input[name*="confirm"], input[name*="retype"], ' +
                        'input[placeholder*="confirm"], input[placeholder*="retype"], ' +
                        'input[id*="confirm_password"], input[id*="password2"]'
                    );
                    if (confirmPwd) return true;

                    return false;
                }}
            """)

            if has_creation_content:
                logger.warning(f"ACCOUNT CREATION CONTENT DETECTED: {self._page.url}")
                return True
        except Exception as e:
            logger.debug(f"Account creation check error: {e}")

        return False
