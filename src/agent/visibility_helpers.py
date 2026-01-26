"""Visibility and scrolling helpers for element interaction."""
import logging

from playwright.sync_api import Locator, Page as PlaywrightPage

logger = logging.getLogger(__name__)

DEFAULT_HEADER_HEIGHT: int = 60


def get_sticky_header_height(page: PlaywrightPage) -> int:
    """Detect sticky/fixed headers and return their height."""
    try:
        return page.evaluate('''() => {
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
        return DEFAULT_HEADER_HEIGHT


def scroll_element_into_view(page: PlaywrightPage, locator: Locator) -> bool:
    """Scroll page to bring element to viewport center, accounting for sticky headers."""
    try:
        box = locator.bounding_box(timeout=2000)
        if not box:
            locator.scroll_into_view_if_needed(timeout=2000)
            return True

        viewport = page.viewport_size
        if not viewport:
            locator.scroll_into_view_if_needed(timeout=2000)
            return True

        header_offset = get_sticky_header_height(page)
        usable_height = viewport['height'] - header_offset
        target_y = box['y'] - header_offset - (usable_height / 2) + (box['height'] / 2)

        page.evaluate(f"window.scrollTo({{top: {target_y}, behavior: 'smooth'}})")
        page.wait_for_timeout(500)
        return True
    except Exception as e:
        logger.debug(f"Scroll error - {e}")
        return False


def verify_element_visible(page: PlaywrightPage, locator: Locator, max_attempts: int = 3) -> bool:
    """Verify element visibility with retry scrolling."""
    for attempt in range(max_attempts):
        try:
            if locator.is_visible(timeout=1000):
                return True
            locator.scroll_into_view_if_needed(timeout=2000)
            page.wait_for_timeout(300)
        except Exception:
            pass
    return False


def wait_for_element_stable(page: PlaywrightPage, locator: Locator, timeout_ms: int = 2000) -> bool:
    """Wait for element position to stabilize."""
    try:
        initial_box = locator.bounding_box(timeout=timeout_ms)
        if not initial_box:
            return False

        page.wait_for_timeout(100)
        final_box = locator.bounding_box(timeout=500)
        if not final_box:
            return False

        position_stable = (
            abs(initial_box['x'] - final_box['x']) < 5 and
            abs(initial_box['y'] - final_box['y']) < 5
        )
        return position_stable
    except Exception:
        return False
