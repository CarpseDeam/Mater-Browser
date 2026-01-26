"""Vision-based fallback for element detection when DOM fails."""
import base64
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from anthropic import Anthropic
from playwright.sync_api import Page

logger = logging.getLogger(__name__)


@dataclass
class VisualElement:
    """Element found via vision."""
    description: str
    x: int
    y: int
    confidence: str


class VisionFallback:
    """Uses Claude vision to find elements when DOM detection fails."""

    def __init__(self, page: Page, api_key: Optional[str] = None) -> None:
        self._page = page
        self._client = Anthropic(api_key=api_key) if api_key else Anthropic()

    def find_apply_button(self) -> Optional[Tuple[int, int]]:
        """
        Take screenshot and ask Claude to locate the Apply button.

        Returns:
            Tuple of (x, y) click coordinates, or None if not found.
        """
        logger.info("VisionFallback: Taking screenshot to find Apply button")

        try:
            screenshot_bytes = self._page.screenshot(full_page=False)
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

            viewport = self._page.viewport_size
            width = viewport["width"] if viewport else 1920
            height = viewport["height"] if viewport else 1080

            response = self._client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=256,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": screenshot_b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": f"""Find the Apply button on this job page screenshot.

Look for buttons or links with text like:
- "Apply"
- "Apply Now"
- "Apply for this job"
- "Easy Apply"
- "Apply on company site"

The viewport is {width}x{height} pixels.

If you find an Apply button, respond with ONLY the coordinates in this exact format:
FOUND: x,y

Where x,y is the CENTER of the button.

If there is no Apply button visible, respond with ONLY:
NOT_FOUND

Do not explain or add any other text."""
                            }
                        ],
                    }
                ],
            )

            result = response.content[0].text.strip()
            logger.info(f"VisionFallback response: {result}")

            if result.startswith("FOUND:"):
                coords = result.replace("FOUND:", "").strip()
                x, y = map(int, coords.split(","))

                if 0 <= x <= width and 0 <= y <= height:
                    logger.info(f"VisionFallback: Found Apply button at ({x}, {y})")
                    return (x, y)
                else:
                    logger.warning(f"VisionFallback: Coordinates ({x}, {y}) outside viewport")
                    return None
            else:
                logger.info("VisionFallback: No Apply button found in screenshot")
                return None

        except Exception as e:
            logger.error(f"VisionFallback error: {e}")
            return None

    def click_at_coordinates(self, x: int, y: int) -> bool:
        """Click at the specified coordinates."""
        try:
            logger.info(f"VisionFallback: Clicking at ({x}, {y})")
            self._page.mouse.click(x, y)
            self._page.wait_for_timeout(2000)
            return True
        except Exception as e:
            logger.error(f"VisionFallback click failed: {e}")
            return False

    def find_and_click_apply(self) -> bool:
        """Combined method: find Apply button and click it."""
        coords = self.find_apply_button()
        if coords:
            return self.click_at_coordinates(coords[0], coords[1])
        return False
