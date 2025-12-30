"""
USENIX Security Symposium paper crawler
"""

import logging
import re
import time
from pathlib import Path
from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..core.base_crawler import BaseCrawler, PaperInfo
from ..config import DATA_DIR

logger = logging.getLogger(__name__)


class USENIXSecurityCrawler(BaseCrawler):
    """USENIX Security Symposium paper crawler"""

    BASE_URL = "https://www.usenix.org"
    CONF_BASE = "https://www.usenix.org/conference/usenixsecurity"

    def __init__(
        self,
        base_dir: Path = None,
        delay: float = 1.0,
        max_workers: int = 5,
        metadata_format: str = 'csv',
    ):
        """
        Initialize crawler

        Args:
            base_dir: Base directory for data storage
            delay: Delay between requests in seconds
            max_workers: Maximum concurrent download threads
            metadata_format: Format for metadata files
        """
        if base_dir is None:
            base_dir = DATA_DIR

        super().__init__(
            conference="USENIX Security",
            conference_dir="USENIX_Security",
            base_dir=base_dir,
            delay=delay,
            max_workers=max_workers,
            metadata_format=metadata_format,
        )

    def get_paper_list(self, year: int) -> List[PaperInfo]:
        """
        Get list of papers for a specific year

        Args:
            year: Conference year

        Returns:
            List of PaperInfo objects
        """
        logger.info(f"Fetching paper list for USENIX Security {year}")

        # Get paper page URLs (may have multiple for summer/fall)
        page_urls = self._get_papers_urls(year)
        if not page_urls:
            logger.warning(f"No conference page found for {year}")
            return []

        # Extract papers from all pages
        papers = []
        seen_titles = set()

        for url in page_urls:
            page_papers = self._extract_papers_from_page(url, year)
            for paper in page_papers:
                title_key = paper.title.lower()[:50]
                if title_key not in seen_titles:
                    seen_titles.add(title_key)
                    papers.append(paper)
            logger.info(f"Extracted {len(page_papers)} papers from {url}")

        logger.info(f"Total {len(papers)} unique papers found for {year}")
        return papers

    def _get_papers_urls(self, year: int) -> List[str]:
        """
        Get paper page URLs for a specific year

        Args:
            year: Conference year

        Returns:
            List of valid URLs
        """
        year_short = str(year)[-2:]
        session = self.session_manager.create_session()

        # Check for multi-page structure (summer + fall) - 2023 and later
        multi_page_urls = [
            (f"{self.CONF_BASE}{year_short}/summer-accepted-papers",
             f"{self.CONF_BASE}{year_short}/fall-accepted-papers"),
            (f"{self.CONF_BASE}{year}/summer-accepted-papers",
             f"{self.CONF_BASE}{year}/fall-accepted-papers"),
        ]

        for summer_url, fall_url in multi_page_urls:
            found_urls = []
            for url in [summer_url, fall_url]:
                try:
                    response = session.get(url, timeout=10)
                    if response.status_code == 200:
                        logger.info(f"Found conference page: {url}")
                        found_urls.append(url)
                except Exception as e:
                    logger.debug(f"Failed to access {url}: {e}")
            if found_urls:
                session.close()
                return found_urls

        # Single page URL fallbacks
        single_urls = [
            f"{self.CONF_BASE}{year}/technical-sessions",
            f"{self.CONF_BASE}{year_short}/technical-sessions",
            f"{self.CONF_BASE}{year}/program",
            f"{self.CONF_BASE}{year_short}/program",
            f"{self.CONF_BASE}{year}/papers",
            f"{self.CONF_BASE}{year_short}/papers",
        ]

        for url in single_urls:
            try:
                response = session.get(url, timeout=10)
                if response.status_code == 200:
                    logger.info(f"Found conference page: {url}")
                    session.close()
                    return [url]
            except Exception as e:
                logger.debug(f"Failed to access {url}: {e}")

        session.close()
        return []

    def _extract_papers_from_page(self, url: str, year: int) -> List[PaperInfo]:
        """
        Extract paper information from a page

        Args:
            url: Page URL
            year: Conference year

        Returns:
            List of PaperInfo objects
        """
        papers = []
        session = self.session_manager.create_session()

        try:
            response = session.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Method 1: Find presentation page links
            paper_links = soup.find_all('a', href=re.compile(r'/conference/usenixsecurity\d+/presentation/'))
            seen_urls = set()

            logger.info(f"Found {len(paper_links)} presentation links")

            for idx, link in enumerate(paper_links):
                href = link.get('href', '')
                if href in seen_urls:
                    continue
                seen_urls.add(href)

                paper_url = urljoin(self.BASE_URL, href)
                title = link.get_text(strip=True)

                # Try to get title from parent element if empty
                if not title or len(title) < 10:
                    parent = link.find_parent(['li', 'div', 'article'])
                    if parent:
                        title_elem = parent.find(['h3', 'h4', 'strong', 'a'])
                        if title_elem:
                            title = title_elem.get_text(strip=True)

                if not title or len(title) < 10:
                    continue

                # Try to infer PDF URL from presentation URL
                year_match = re.search(r'usenixsecurity(\d+)', href)
                if year_match:
                    year_str = year_match.group(1)
                    slug = href.split('/')[-1]

                    # Try common PDF URL patterns
                    possible_pdf_urls = [
                        f"{self.BASE_URL}/system/files/sec{year_str}_{slug}.pdf",
                        f"{self.BASE_URL}/system/files/conference/usenixsecurity{year_str}/sec{year_str}_{slug}.pdf",
                        f"{self.BASE_URL}/sites/default/files/sec{year_str}_paper_{slug}.pdf",
                        f"{self.BASE_URL}/sites/default/files/{slug}.pdf",
                    ]

                    pdf_url = None
                    for test_url in possible_pdf_urls:
                        try:
                            test_response = session.head(test_url, timeout=5, allow_redirects=True)
                            if test_response.status_code == 200:
                                content_type = test_response.headers.get('Content-Type', '').lower()
                                if 'pdf' in content_type:
                                    pdf_url = test_url
                                    break
                        except Exception:
                            continue

                    # If no direct URL found, visit presentation page
                    if not pdf_url:
                        pdf_url, authors = self._get_pdf_from_presentation(paper_url, session)
                    else:
                        authors = ''

                    if pdf_url:
                        papers.append(PaperInfo(
                            title=title,
                            authors=authors,
                            pdf_url=pdf_url,
                            source='USENIX',
                        ))

                time.sleep(self.delay * 0.3)

            # Method 2: Find direct PDF links
            pdf_links = soup.find_all('a', href=re.compile(r'\.pdf$', re.I))
            for link in pdf_links:
                pdf_url = link.get('href', '')
                if pdf_url:
                    if not pdf_url.startswith('http'):
                        pdf_url = urljoin(self.BASE_URL, pdf_url)

                    title = link.text.strip()
                    if not title:
                        parent = link.find_parent(['div', 'li', 'td', 'article'])
                        if parent:
                            title_elem = parent.find(['h3', 'h4', 'strong', 'span'],
                                                     class_=re.compile(r'title|paper', re.I))
                            if title_elem:
                                title = title_elem.get_text(strip=True)

                    if title and len(title) >= 10:
                        # Check for duplicates
                        if not any(p.pdf_url == pdf_url for p in papers):
                            papers.append(PaperInfo(
                                title=title,
                                pdf_url=pdf_url,
                                source='USENIX',
                            ))

        except Exception as e:
            logger.error(f"Failed to extract papers from {url}: {e}")
        finally:
            session.close()

        return papers

    def _get_pdf_from_presentation(self, paper_url: str, session) -> tuple:
        """
        Get PDF URL from presentation page

        Args:
            paper_url: Presentation page URL
            session: requests Session

        Returns:
            Tuple of (pdf_url, authors) or (None, '')
        """
        try:
            response = session.get(paper_url, timeout=10)
            if response.status_code != 200:
                return None, ''

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find PDF link
            pdf_link = soup.find('a', href=re.compile(r'\.pdf$', re.I))
            if not pdf_link:
                # Try finding links with 'paper' in href
                all_links = soup.find_all('a', href=True)
                for link in all_links:
                    href = link.get('href', '')
                    if 'paper' in href.lower() and '.pdf' in href.lower():
                        pdf_link = link
                        break

            pdf_url = None
            if pdf_link:
                pdf_url = pdf_link.get('href', '')
                if not pdf_url.startswith('http'):
                    pdf_url = urljoin(self.BASE_URL, pdf_url)

            # Extract authors
            authors = ''
            authors_elem = soup.find(['div', 'p'], class_=re.compile(r'author', re.I))
            if authors_elem:
                authors = authors_elem.get_text(strip=True)

            return pdf_url, authors

        except Exception as e:
            logger.debug(f"Failed to get PDF from presentation page {paper_url}: {e}")
            return None, ''
