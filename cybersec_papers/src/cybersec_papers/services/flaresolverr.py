"""
FlareSolverr client for bypassing Cloudflare protection
"""

import logging
from typing import Optional, List, Dict, Tuple

import requests

from ..config import FLARESOLVERR_URL

logger = logging.getLogger(__name__)


class FlareSolverrClient:
    """Client for FlareSolverr service"""

    def __init__(self, url: str = FLARESOLVERR_URL):
        """
        Initialize FlareSolverr client

        Args:
            url: FlareSolverr service URL
        """
        self.url = url
        self._available: Optional[bool] = None

    def check_available(self) -> bool:
        """
        Check if FlareSolverr service is available

        Returns:
            True if service is available
        """
        if self._available is not None:
            return self._available

        try:
            # Try health endpoint first
            health_url = self.url.replace('/v1', '/health')
            response = requests.get(health_url, timeout=5)
            self._available = response.status_code == 200
        except Exception:
            try:
                # Try root endpoint as fallback
                root_url = self.url.replace('/v1', '/')
                response = requests.get(root_url, timeout=5)
                self._available = response.status_code == 200
            except Exception:
                self._available = False

        if self._available:
            logger.info("FlareSolverr service available")
        else:
            logger.warning("FlareSolverr service not available")

        return self._available

    def get_cookies(
        self,
        target_url: str,
        max_timeout: int = 90000,
    ) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """
        Get cookies by visiting a URL through FlareSolverr

        Args:
            target_url: URL to visit
            max_timeout: Maximum timeout in milliseconds

        Returns:
            Tuple of (cookies list, user_agent) or (None, None) on failure
        """
        if not self.check_available():
            return None, None

        try:
            payload = {
                'cmd': 'request.get',
                'url': target_url,
                'maxTimeout': max_timeout,
            }

            logger.info(f"Getting cookies via FlareSolverr: {target_url[:60]}...")
            response = requests.post(self.url, json=payload, timeout=max_timeout / 1000 + 10)

            if response.status_code != 200:
                logger.warning(f"FlareSolverr returned {response.status_code}")
                return None, None

            data = response.json()

            if data.get('status') != 'ok':
                logger.warning(f"FlareSolverr status: {data.get('status')}, message: {data.get('message')}")
                return None, None

            solution = data.get('solution', {})
            cookies = solution.get('cookies', [])
            user_agent = solution.get('userAgent', '')

            if not cookies:
                logger.warning("FlareSolverr returned no cookies")
                return None, None

            logger.info(f"Got {len(cookies)} cookies from FlareSolverr")
            return cookies, user_agent

        except requests.exceptions.Timeout:
            logger.warning("FlareSolverr request timed out")
            return None, None
        except Exception as e:
            logger.error(f"FlareSolverr error: {e}")
            return None, None

    def fetch_page(
        self,
        url: str,
        max_timeout: int = 60000,
    ) -> Optional[str]:
        """
        Fetch a page through FlareSolverr

        Args:
            url: URL to fetch
            max_timeout: Maximum timeout in milliseconds

        Returns:
            Page HTML content or None on failure
        """
        if not self.check_available():
            return None

        try:
            payload = {
                'cmd': 'request.get',
                'url': url,
                'maxTimeout': max_timeout,
            }

            response = requests.post(self.url, json=payload, timeout=max_timeout / 1000 + 10)

            if response.status_code != 200:
                return None

            data = response.json()

            if data.get('status') != 'ok':
                return None

            solution = data.get('solution', {})
            return solution.get('response', '')

        except Exception as e:
            logger.debug(f"FlareSolverr fetch error: {e}")
            return None
