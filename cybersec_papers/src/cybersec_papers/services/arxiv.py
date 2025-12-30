"""
arXiv API client for finding open access papers
"""

import logging
import re
import xml.etree.ElementTree as ET
from typing import Optional, Tuple
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)


class ArxivClient:
    """Client for arXiv API"""

    API_BASE = "http://export.arxiv.org/api/query"

    def __init__(self):
        """Initialize client"""
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/atom+xml',
        })

    def find_paper(
        self,
        title: Optional[str] = None,
        arxiv_id: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Find paper on arXiv and get PDF URL

        Args:
            title: Paper title
            arxiv_id: arXiv ID (e.g., "2301.12345")

        Returns:
            Tuple of (pdf_url, arxiv_id) or (None, None)
        """
        # Try by arXiv ID first
        if arxiv_id:
            result = self._get_by_id(arxiv_id)
            if result:
                return result

        # Fallback to title search
        if title:
            result = self._search_by_title(title)
            if result:
                return result

        return None, None

    def _get_by_id(self, arxiv_id: str) -> Optional[Tuple[str, str]]:
        """
        Get paper by arXiv ID

        Args:
            arxiv_id: arXiv ID

        Returns:
            Tuple of (pdf_url, arxiv_id) or None
        """
        # Clean up the ID
        arxiv_id = self._normalize_arxiv_id(arxiv_id)
        if not arxiv_id:
            return None

        try:
            params = {
                'id_list': arxiv_id,
                'max_results': 1,
            }

            response = self.session.get(self.API_BASE, params=params, timeout=15)

            if response.status_code != 200:
                return None

            # Parse the Atom feed
            root = ET.fromstring(response.content)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}

            entries = root.findall('atom:entry', ns)
            if not entries:
                return None

            entry = entries[0]

            # Get PDF link
            for link in entry.findall('atom:link', ns):
                if link.get('title') == 'pdf':
                    pdf_url = link.get('href')
                    if pdf_url:
                        # Ensure it ends with .pdf
                        if not pdf_url.endswith('.pdf'):
                            pdf_url = pdf_url + '.pdf'
                        return pdf_url, arxiv_id

        except Exception as e:
            logger.debug(f"arXiv ID lookup failed: {e}")

        return None

    def _search_by_title(self, title: str) -> Optional[Tuple[str, str]]:
        """
        Search for paper by title

        Args:
            title: Paper title

        Returns:
            Tuple of (pdf_url, arxiv_id) or None
        """
        try:
            # Clean title for search
            clean_title = self._clean_title_for_search(title)

            params = {
                'search_query': f'ti:"{clean_title}"',
                'max_results': 5,
                'sortBy': 'relevance',
            }

            response = self.session.get(self.API_BASE, params=params, timeout=15)

            if response.status_code != 200:
                return None

            # Parse the Atom feed
            root = ET.fromstring(response.content)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}

            entries = root.findall('atom:entry', ns)

            # Find best match
            from ..core.utils import titles_match

            for entry in entries:
                entry_title_elem = entry.find('atom:title', ns)
                if entry_title_elem is None:
                    continue

                entry_title = entry_title_elem.text
                if entry_title and titles_match(title, entry_title):
                    # Get arXiv ID from entry ID
                    id_elem = entry.find('atom:id', ns)
                    if id_elem is not None and id_elem.text:
                        arxiv_id = self._extract_arxiv_id(id_elem.text)

                        # Get PDF link
                        for link in entry.findall('atom:link', ns):
                            if link.get('title') == 'pdf':
                                pdf_url = link.get('href')
                                if pdf_url:
                                    if not pdf_url.endswith('.pdf'):
                                        pdf_url = pdf_url + '.pdf'
                                    return pdf_url, arxiv_id

        except Exception as e:
            logger.debug(f"arXiv title search failed: {e}")

        return None

    @staticmethod
    def _normalize_arxiv_id(arxiv_id: str) -> Optional[str]:
        """
        Normalize arXiv ID to standard format

        Args:
            arxiv_id: Raw arXiv ID

        Returns:
            Normalized ID or None
        """
        if not arxiv_id:
            return None

        # Remove common prefixes
        arxiv_id = arxiv_id.strip()
        arxiv_id = re.sub(r'^arXiv:', '', arxiv_id, flags=re.IGNORECASE)
        arxiv_id = re.sub(r'^https?://arxiv\.org/abs/', '', arxiv_id)
        arxiv_id = re.sub(r'^https?://arxiv\.org/pdf/', '', arxiv_id)
        arxiv_id = re.sub(r'\.pdf$', '', arxiv_id)

        # Validate format (new format: YYMM.NNNNN or old format: category/YYMMNNN)
        if re.match(r'^\d{4}\.\d{4,5}(v\d+)?$', arxiv_id):
            return arxiv_id
        if re.match(r'^[a-z-]+/\d{7}(v\d+)?$', arxiv_id):
            return arxiv_id

        return None

    @staticmethod
    def _extract_arxiv_id(url: str) -> Optional[str]:
        """
        Extract arXiv ID from URL or ID string

        Args:
            url: URL or ID string

        Returns:
            arXiv ID or None
        """
        # Match new format (YYMM.NNNNN)
        match = re.search(r'(\d{4}\.\d{4,5})(v\d+)?', url)
        if match:
            return match.group(1) + (match.group(2) or '')

        # Match old format (category/YYMMNNN)
        match = re.search(r'([a-z-]+/\d{7})(v\d+)?', url)
        if match:
            return match.group(1) + (match.group(2) or '')

        return None

    @staticmethod
    def _clean_title_for_search(title: str) -> str:
        """
        Clean title for arXiv search query

        Args:
            title: Original title

        Returns:
            Cleaned title
        """
        # Remove special characters that might break the query
        title = re.sub(r'[^\w\s-]', ' ', title)
        # Collapse whitespace
        title = ' '.join(title.split())
        return title
