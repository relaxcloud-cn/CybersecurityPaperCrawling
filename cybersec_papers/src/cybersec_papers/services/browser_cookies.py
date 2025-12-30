"""
Browser-based cookie extraction for bypassing Cloudflare

Uses Playwright to automate a real browser and extract cookies after
passing Cloudflare challenges.
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class BrowserCookieExtractor:
    """Extract cookies from websites using a real browser (Playwright)"""

    def __init__(self, headless: bool = True, timeout: int = 60):
        """
        Initialize browser cookie extractor

        Args:
            headless: Run browser in headless mode
            timeout: Timeout for page load in seconds
        """
        self.headless = headless
        self.timeout = timeout * 1000  # Playwright uses milliseconds
        self._browser = None
        self._playwright = None

    def get_cookies(
        self,
        url: str,
        wait_for_cloudflare: bool = True,
        save_path: Optional[Path] = None,
    ) -> List[Dict]:
        """
        Get cookies from a URL by visiting it with a real browser

        Args:
            url: URL to visit
            wait_for_cloudflare: Wait for Cloudflare challenge to complete
            save_path: Optional path to save cookies as JSON

        Returns:
            List of cookie dictionaries
        """
        try:
            from playwright.sync_api import sync_playwright

            logger.info(f"Starting browser to get cookies from {url[:50]}...")

            with sync_playwright() as p:
                # Launch Firefox (better at bypassing detection)
                browser = p.firefox.launch(
                    headless=self.headless,
                    # Firefox-specific args for better stealth
                    firefox_user_prefs={
                        "dom.webdriver.enabled": False,
                        "useAutomationExtension": False,
                    }
                )

                # Create context with realistic settings
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
                        "Gecko/20100101 Firefox/128.0"
                    ),
                    locale="en-US",
                    timezone_id="America/New_York",
                )

                page = context.new_page()

                # Navigate to URL
                logger.info("Navigating to page...")
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)

                # Wait for Cloudflare challenge if needed
                if wait_for_cloudflare:
                    self._wait_for_cloudflare(page)

                # Get cookies
                cookies = context.cookies()
                logger.info(f"Got {len(cookies)} cookies")

                # Save cookies if path provided
                if save_path and cookies:
                    self._save_cookies(cookies, save_path)

                browser.close()

                return cookies

        except ImportError:
            logger.error("Playwright not installed. Run: uv add playwright && playwright install firefox")
            return []
        except Exception as e:
            logger.error(f"Failed to get cookies: {e}")
            return []

    def _wait_for_cloudflare(self, page, max_wait: int = 30):
        """
        Wait for Cloudflare challenge to complete

        Args:
            page: Playwright page object
            max_wait: Maximum wait time in seconds
        """
        start_time = time.time()

        while time.time() - start_time < max_wait:
            title = page.title().lower()
            content = page.content().lower()

            # Check if still on Cloudflare challenge page
            if "just a moment" in title or "checking your browser" in content:
                logger.debug("Waiting for Cloudflare challenge...")
                time.sleep(2)
                continue

            # Check if challenge completed
            if "cloudflare" not in content or "cf-" not in content:
                logger.info("Cloudflare challenge completed!")
                # Give page a moment to fully load
                time.sleep(2)
                return

            time.sleep(1)

        logger.warning(f"Cloudflare wait timeout after {max_wait}s")

    def _save_cookies(self, cookies: List[Dict], path: Path):
        """Save cookies to JSON file"""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w') as f:
                json.dump(cookies, f, indent=2)
            logger.info(f"Cookies saved to {path}")
        except Exception as e:
            logger.error(f"Failed to save cookies: {e}")

    @staticmethod
    def load_cookies(path: Path) -> List[Dict]:
        """Load cookies from JSON file"""
        try:
            if path.exists():
                with open(path, 'r') as f:
                    cookies = json.load(f)
                logger.info(f"Loaded {len(cookies)} cookies from {path}")
                return cookies
        except Exception as e:
            logger.error(f"Failed to load cookies: {e}")
        return []

    @staticmethod
    def cookies_to_requests_format(cookies: List[Dict]) -> Dict[str, str]:
        """Convert Playwright cookies to requests library format"""
        return {c['name']: c['value'] for c in cookies}


def get_acm_cookies(
    save_path: Optional[Path] = None,
    headless: bool = True,
) -> List[Dict]:
    """
    Convenience function to get ACM DL cookies

    Args:
        save_path: Path to save cookies
        headless: Run browser in headless mode

    Returns:
        List of cookie dictionaries
    """
    extractor = BrowserCookieExtractor(headless=headless, timeout=90)

    # Try to get cookies from ACM DL
    # Using a specific paper page that requires passing Cloudflare
    test_url = "https://dl.acm.org/doi/10.1145/3372297.3423349"

    cookies = extractor.get_cookies(
        url=test_url,
        wait_for_cloudflare=True,
        save_path=save_path,
    )

    return cookies


if __name__ == "__main__":
    # Test the cookie extractor
    import sys
    logging.basicConfig(level=logging.INFO)

    save_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    headless = "--no-headless" not in sys.argv

    cookies = get_acm_cookies(save_path=save_path, headless=headless)
    print(f"\nGot {len(cookies)} cookies")

    if cookies:
        cf_cookies = [c for c in cookies if 'cf' in c['name'].lower()]
        print(f"Cloudflare cookies: {[c['name'] for c in cf_cookies]}")
