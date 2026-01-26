"""PaymentBlocker prevents accidental purchases during job applications."""
import re
from dataclasses import dataclass


@dataclass
class BlockDecision:
    should_block: bool
    reason: str | None
    confidence: float


BLOCK_URL_PATTERNS: list[str] = [
    "/checkout",
    "/payment",
    "/subscribe",
    "/premium",
    "/upgrade",
    "/billing",
]

ALLOW_URL_PATTERNS: list[str] = [
    "/apply",
    "/submit",
    "/application",
    "/confirmed",
]

PURCHASE_BUTTON_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"complete\s+purchase", re.IGNORECASE),
    re.compile(r"subscribe\s+now", re.IGNORECASE),
    re.compile(r"buy\s+now", re.IGNORECASE),
    re.compile(r"upgrade\s+to\s+premium", re.IGNORECASE),
    re.compile(r"get\s+premium", re.IGNORECASE),
    re.compile(r"try\s+premium", re.IGNORECASE),
]

CREDIT_CARD_INPUT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'name=["\']?(?:card[-_]?number|cc[-_]?number|creditcard)', re.IGNORECASE),
    re.compile(r'name=["\']?(?:cvv|cvc|ccv|security[-_]?code)', re.IGNORECASE),
    re.compile(r'name=["\']?(?:expir|exp[-_]?date|cc[-_]?exp)', re.IGNORECASE),
    re.compile(r'placeholder=["\']?(?:card\s*number|credit\s*card)', re.IGNORECASE),
    re.compile(r'placeholder=["\']?(?:mm\s*/\s*yy|mm/yy|expir)', re.IGNORECASE),
    re.compile(r'placeholder=["\']?(?:cvc|cvv|security)', re.IGNORECASE),
    re.compile(r'autocomplete=["\']?cc-', re.IGNORECASE),
]

PREMIUM_UPSELL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"indeed\s+premium", re.IGNORECASE),
    re.compile(r"linkedin\s+premium", re.IGNORECASE),
]

JOB_APPLICATION_SIGNALS: list[re.Pattern[str]] = [
    re.compile(r"submit\s+application", re.IGNORECASE),
    re.compile(r"apply\s+now", re.IGNORECASE),
    re.compile(r"application[-_]?form", re.IGNORECASE),
    re.compile(r'name=["\']?resume', re.IGNORECASE),
    re.compile(r"application\s+submitted", re.IGNORECASE),
    re.compile(r"thank\s+you\s+for\s+applying", re.IGNORECASE),
]

JOB_LISTING_SIGNALS: list[re.Pattern[str]] = [
    re.compile(r"<h1[^>]*>.*(?:engineer|developer|manager|analyst|designer)", re.IGNORECASE),
    re.compile(r"job[-_]?listing", re.IGNORECASE),
    re.compile(r"we\s+are\s+looking\s+for", re.IGNORECASE),
]


class PaymentBlocker:
    def should_block(self, url: str, page_content: str) -> BlockDecision:
        url_lower = url.lower()

        is_job_app_url = any(pattern in url_lower for pattern in ALLOW_URL_PATTERNS)
        is_payment_url = any(pattern in url_lower for pattern in BLOCK_URL_PATTERNS)

        has_job_signals = any(p.search(page_content) for p in JOB_APPLICATION_SIGNALS)
        has_job_listing = any(p.search(page_content) for p in JOB_LISTING_SIGNALS)

        if is_job_app_url or has_job_signals:
            return BlockDecision(
                should_block=False,
                reason=None,
                confidence=0.9
            )

        if has_job_listing and not self._has_payment_content(page_content):
            return BlockDecision(
                should_block=False,
                reason=None,
                confidence=0.8
            )

        if is_payment_url:
            if has_job_listing:
                return BlockDecision(
                    should_block=False,
                    reason=None,
                    confidence=0.7
                )
            return BlockDecision(
                should_block=True,
                reason=f"URL contains payment pattern",
                confidence=0.9
            )

        credit_card_detected = any(p.search(page_content) for p in CREDIT_CARD_INPUT_PATTERNS)
        if credit_card_detected:
            return BlockDecision(
                should_block=True,
                reason="Credit card input fields detected",
                confidence=0.95
            )

        purchase_button_detected = any(p.search(page_content) for p in PURCHASE_BUTTON_PATTERNS)
        if purchase_button_detected:
            return BlockDecision(
                should_block=True,
                reason="Purchase button detected",
                confidence=0.9
            )

        premium_upsell_detected = any(p.search(page_content) for p in PREMIUM_UPSELL_PATTERNS)
        if premium_upsell_detected:
            if "see detailed" in page_content.lower() or "premium-hint" in page_content.lower():
                return BlockDecision(
                    should_block=False,
                    reason=None,
                    confidence=0.6
                )
            return BlockDecision(
                should_block=True,
                reason="Premium upsell detected",
                confidence=0.85
            )

        return BlockDecision(
            should_block=False,
            reason=None,
            confidence=0.5
        )

    def _has_payment_content(self, content: str) -> bool:
        return (
            any(p.search(content) for p in CREDIT_CARD_INPUT_PATTERNS) or
            any(p.search(content) for p in PURCHASE_BUTTON_PATTERNS)
        )
