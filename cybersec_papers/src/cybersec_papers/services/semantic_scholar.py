"""
Semantic Scholar API client for finding open access papers
"""

import logging
from typing import Optional, Tuple

import requests

logger = logging.getLogger(__name__)


class SemanticScholarClient:
    """Client for Semantic Scholar API"""

    API_BASE = "https://api.semanticscholar.org/graph/v1"

    def __init__(self):
        """Initialize client"""
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
        })

    def find_open_access_pdf(
        self,
        doi: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Find open access PDF URL for a paper

        Args:
            doi: Paper DOI
            title: Paper title (fallback if no DOI)

        Returns:
            Tuple of (pdf_url, source) or (None, None)
        """
        # Try by DOI first
        if doi:
            result = self._search_by_doi(doi)
            if result:
                return result

        # Fallback to title search
        if title:
            result = self._search_by_title(title)
            if result:
                return result

        return None, None

    def _search_by_doi(self, doi: str) -> Optional[Tuple[str, str]]:
        """
        Search for paper by DOI

        Args:
            doi: Paper DOI

        Returns:
            Tuple of (pdf_url, source) or None
        """
        try:
            url = f"{self.API_BASE}/paper/DOI:{doi}"
            params = {'fields': 'title,openAccessPdf,externalIds'}

            response = self.session.get(url, params=params, timeout=15)

            if response.status_code != 200:
                return None

            data = response.json()
            open_access = data.get('openAccessPdf', {})

            if open_access:
                pdf_url = open_access.get('url', '')
                if pdf_url:
                    # Skip ACM/IEEE URLs that require authentication
                    if 'dl.acm.org' in pdf_url or 'ieeexplore.ieee.org' in pdf_url:
                        logger.debug(f"Skipping paywalled URL: {pdf_url[:50]}")
                    elif 'arxiv.org' in pdf_url:
                        return pdf_url, 'arXiv'
                    elif 'eprint.iacr.org' in pdf_url:
                        return pdf_url, 'IACR'
                    else:
                        return pdf_url, 'Semantic Scholar'

        except Exception as e:
            logger.debug(f"Semantic Scholar DOI search failed: {e}")

        return None

    def _search_by_title(self, title: str) -> Optional[Tuple[str, str]]:
        """
        Search for paper by title

        Args:
            title: Paper title

        Returns:
            Tuple of (pdf_url, source) or None
        """
        try:
            url = f"{self.API_BASE}/paper/search"
            params = {
                'query': title,
                'fields': 'title,openAccessPdf',
                'limit': 3,
            }

            response = self.session.get(url, params=params, timeout=15)

            if response.status_code != 200:
                return None

            data = response.json()
            papers = data.get('data', [])

            # Find best match
            from ..core.utils import titles_match

            for paper in papers:
                if titles_match(title, paper.get('title', '')):
                    open_access = paper.get('openAccessPdf', {})
                    if open_access:
                        pdf_url = open_access.get('url', '')
                        if pdf_url:
                            # Skip ACM/IEEE URLs that require authentication
                            if 'dl.acm.org' in pdf_url or 'ieeexplore.ieee.org' in pdf_url:
                                continue
                            elif 'arxiv.org' in pdf_url:
                                return pdf_url, 'arXiv'
                            elif 'eprint.iacr.org' in pdf_url:
                                return pdf_url, 'IACR'
                            else:
                                return pdf_url, 'Semantic Scholar'

        except Exception as e:
            logger.debug(f"Semantic Scholar title search failed: {e}")

        return None
