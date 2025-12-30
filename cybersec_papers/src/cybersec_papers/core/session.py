"""
Session management for HTTP requests
"""

import requests
from typing import Optional, Dict, List


class SessionManager:
    """Manages HTTP sessions with configurable headers and cookies"""

    DEFAULT_HEADERS = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
    }

    def __init__(
        self,
        user_agent: Optional[str] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize session manager

        Args:
            user_agent: Custom User-Agent string
            extra_headers: Additional headers to include
        """
        self.user_agent = user_agent
        self.extra_headers = extra_headers or {}
        self._session: Optional[requests.Session] = None

    def create_session(
        self,
        cookies: Optional[List[Dict]] = None,
    ) -> requests.Session:
        """
        Create a new session with configured headers

        Args:
            cookies: List of cookie dicts from FlareSolverr

        Returns:
            Configured requests.Session
        """
        session = requests.Session()

        # Set headers
        headers = self.DEFAULT_HEADERS.copy()
        if self.user_agent:
            headers['User-Agent'] = self.user_agent
        headers.update(self.extra_headers)
        session.headers.update(headers)

        # Add cookies if provided
        if cookies:
            for cookie in cookies:
                session.cookies.set(
                    cookie['name'],
                    cookie['value'],
                    domain=cookie.get('domain', ''),
                    path=cookie.get('path', '/'),
                )

        return session

    def get_session(self) -> requests.Session:
        """
        Get or create the main session

        Returns:
            The main session
        """
        if self._session is None:
            self._session = self.create_session()
        return self._session

    def create_worker_session(self) -> requests.Session:
        """
        Create a new session for worker thread

        Returns:
            New session with same configuration as main session
        """
        session = self.create_session()

        # Copy cookies from main session if exists
        if self._session:
            session.cookies.update(self._session.cookies)

        return session

    def update_cookies(self, cookies: List[Dict]) -> None:
        """
        Update main session cookies

        Args:
            cookies: List of cookie dicts from FlareSolverr
        """
        session = self.get_session()
        for cookie in cookies:
            session.cookies.set(
                cookie['name'],
                cookie['value'],
                domain=cookie.get('domain', ''),
                path=cookie.get('path', '/'),
            )

    def update_user_agent(self, user_agent: str) -> None:
        """
        Update User-Agent in main session

        Args:
            user_agent: New User-Agent string
        """
        self.user_agent = user_agent
        if self._session:
            self._session.headers['User-Agent'] = user_agent
