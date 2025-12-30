"""
NDSS (Network and Distributed System Security Symposium) paper crawler
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


class NDSSCrawler(BaseCrawler):
    """NDSS paper crawler"""

    BASE_URL = "https://www.ndss-symposium.org"

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
            conference="NDSS",
            conference_dir="NDSS",
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
        logger.info(f"Fetching paper list for NDSS {year}")

        # Get paper page URLs
        page_urls = self._get_papers_urls(year)
        if not page_urls:
            logger.warning(f"No conference page found for {year}")
            return []

        # Extract papers
        papers = self._extract_papers(page_urls, year)

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
        urls_to_try = [
            f"{self.BASE_URL}/ndss{year}/accepted-papers/",
            f"{self.BASE_URL}/ndss{year}/program/",
            f"{self.BASE_URL}/ndss{year}/",
            f"{self.BASE_URL}/ndss{year}/papers/",
        ]

        session = self.session_manager.create_session()
        valid_urls = []

        for url in urls_to_try:
            try:
                response = session.get(url, timeout=10)
                if response.status_code == 200:
                    logger.info(f"Found conference page: {url}")
                    valid_urls.append(url)
            except Exception as e:
                logger.debug(f"Failed to access {url}: {e}")

        session.close()
        return valid_urls if valid_urls else []

    def _extract_papers(self, urls: List[str], year: int) -> List[PaperInfo]:
        """
        Extract paper information from pages

        Args:
            urls: Page URLs
            year: Conference year

        Returns:
            List of PaperInfo objects
        """
        papers = []
        seen_urls = set()
        seen_slugs = set()
        session = self.session_manager.create_session()

        for url in urls:
            try:
                response = session.get(url, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')

                # Method 1: Find paper detail page links (/ndss-paper/xxx/)
                detail_links = soup.find_all('a', href=re.compile(r'/ndss-paper/'))
                logger.info(f"Found {len(detail_links)} paper detail links from {url}")

                for link in detail_links:
                    href = link.get('href', '')

                    # Extract slug
                    slug_match = re.search(r'/ndss-paper/([^/]+)/?', href)
                    if not slug_match:
                        continue

                    slug = slug_match.group(1)
                    if slug in seen_slugs:
                        continue
                    seen_slugs.add(slug)

                    # Build detail page URL
                    if not href.startswith('http'):
                        detail_url = urljoin(self.BASE_URL, href)
                    else:
                        detail_url = href

                    # Visit detail page to get PDF and title
                    paper = self._get_paper_from_detail(detail_url, slug, session)
                    if paper and paper.pdf_url not in seen_urls:
                        seen_urls.add(paper.pdf_url)
                        papers.append(paper)

                    time.sleep(self.delay * 0.5)

                # Method 2: Find direct PDF links (backup)
                pdf_links = soup.find_all('a', href=re.compile(r'\.pdf$', re.I))
                for link in pdf_links:
                    pdf_url = link.get('href', '')
                    if pdf_url and pdf_url not in seen_urls:
                        if not pdf_url.startswith('http'):
                            pdf_url = urljoin(self.BASE_URL, pdf_url)

                        # Skip slides
                        if 'slide' in pdf_url.lower():
                            continue

                        seen_urls.add(pdf_url)

                        # Get title
                        title = link.text.strip()
                        if not title or title.lower() in ['pdf', 'download', '[pdf]']:
                            parent = link.find_parent(['div', 'li', 'article', 'section', 'tr'])
                            if parent:
                                title_elem = parent.find(['h3', 'h4', 'h5', 'strong', 'a', 'span'],
                                                         class_=re.compile(r'title|paper', re.I))
                                if title_elem:
                                    title = title_elem.get_text(strip=True)
                                else:
                                    text = parent.get_text(strip=True)
                                    if text:
                                        title = text.split('\n')[0].strip()[:200]

                        if not title:
                            title = f"paper_{len(papers)+1}"

                        if len(title) >= 10:
                            papers.append(PaperInfo(
                                title=title,
                                pdf_url=pdf_url,
                                source='NDSS',
                            ))

            except Exception as e:
                logger.error(f"Failed to extract papers from {url}: {e}")

        session.close()

        # Deduplicate by title
        unique_papers = []
        seen_titles = set()
        for paper in papers:
            title_key = paper.title.lower()[:50]
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique_papers.append(paper)

        return unique_papers

    def _get_paper_from_detail(self, detail_url: str, slug: str, session) -> PaperInfo:
        """
        Get paper information from detail page

        Args:
            detail_url: Detail page URL
            slug: Paper slug
            session: requests Session

        Returns:
            PaperInfo or None
        """
        try:
            response = session.get(detail_url, timeout=10)
            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.text, 'html.parser')

            # Get title
            title = None
            title_elem = soup.find(['h1', 'h2', 'h3'])
            if title_elem:
                title = title_elem.get_text(strip=True)

            if not title or len(title) < 10:
                title_div = soup.find(['div', 'span'], class_=re.compile(r'title', re.I))
                if title_div:
                    title = title_div.get_text(strip=True)

            if not title or len(title) < 10:
                # Infer from slug
                title = slug.replace('-', ' ').title()

            # Find PDF link
            pdf_url = None
            pdf_link = soup.find('a', href=re.compile(r'\.pdf$', re.I))
            if pdf_link:
                pdf_url = pdf_link.get('href', '')
                if not pdf_url.startswith('http'):
                    pdf_url = urljoin(self.BASE_URL, pdf_url)

                # Skip slides, prefer paper PDFs
                if 'slide' in pdf_url.lower():
                    all_pdf_links = soup.find_all('a', href=re.compile(r'\.pdf$', re.I))
                    for alt_pdf in all_pdf_links:
                        alt_href = alt_pdf.get('href', '')
                        if 'paper' in alt_href.lower() and 'slide' not in alt_href.lower():
                            pdf_url = alt_href if alt_href.startswith('http') else urljoin(self.BASE_URL, alt_href)
                            break

            if not pdf_url:
                return None

            # Extract authors
            authors = ''
            authors_elem = soup.find(['div', 'p'], class_=re.compile(r'author', re.I))
            if authors_elem:
                authors = authors_elem.get_text(strip=True)

            return PaperInfo(
                title=title,
                authors=authors,
                pdf_url=pdf_url,
                source='NDSS',
            )

        except Exception as e:
            logger.debug(f"Failed to get paper from detail page {detail_url}: {e}")
            return None
