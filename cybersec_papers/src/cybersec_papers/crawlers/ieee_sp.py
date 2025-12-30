"""
IEEE S&P (IEEE Symposium on Security and Privacy) paper crawler
"""

import logging
import re
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

from bs4 import BeautifulSoup

from ..core.base_crawler import BaseCrawler, PaperInfo
from ..config import DATA_DIR
from ..services import FlareSolverrClient, SemanticScholarClient, ArxivClient

logger = logging.getLogger(__name__)


class IEEESPCrawler(BaseCrawler):
    """IEEE S&P paper crawler - based on IEEE Xplore REST API + FlareSolverr"""

    XPLORE_BASE = "https://ieeexplore.ieee.org"

    # Year -> Proceeding number mapping
    YEAR_PROCEEDING_IDS = {
        2025: "10919321",
        2024: "10646615",
        2023: "10179215",
        2022: "9833550",
        2021: "9519381",
        2020: "9144328",
        2019: "8835275",
        2018: "8418567",
    }

    def __init__(
        self,
        base_dir: Path = None,
        delay: float = 1.0,
        max_workers: int = 5,
        metadata_format: str = 'csv',
        use_flaresolverr: bool = False,
    ):
        """
        Initialize crawler

        Args:
            base_dir: Base directory for data storage
            delay: Delay between requests in seconds
            max_workers: Maximum concurrent download threads
            metadata_format: Format for metadata files
            use_flaresolverr: Whether to use FlareSolverr to bypass anti-bot
        """
        if base_dir is None:
            base_dir = DATA_DIR

        super().__init__(
            conference="IEEE S&P",
            conference_dir="IEEE_SP",
            base_dir=base_dir,
            delay=delay,
            max_workers=max_workers,
            metadata_format=metadata_format,
        )

        self.use_flaresolverr = use_flaresolverr
        self.flaresolverr = FlareSolverrClient()
        self.semantic_scholar = SemanticScholarClient()
        self.arxiv = ArxivClient()
        self.ieee_cookies = None

    def get_paper_list(self, year: int) -> List[PaperInfo]:
        """
        Get list of papers for a specific year

        Args:
            year: Conference year

        Returns:
            List of PaperInfo objects
        """
        logger.info(f"Fetching paper list for IEEE S&P {year}")

        # Check open access status
        current_year = 2024
        if year >= current_year:
            logger.warning(f"Papers from {year} may still be behind paywall (1 year embargo)")

        # Initialize FlareSolverr if enabled
        if self.use_flaresolverr and self.flaresolverr.check_available():
            logger.info("Initializing FlareSolverr for IEEE...")
            cookies, _ = self.flaresolverr.get_cookies(
                f"{self.XPLORE_BASE}/stamp/stamp.jsp?arnumber=9833617"
            )
            if cookies:
                self.ieee_cookies = cookies
                self.session_manager.update_cookies(cookies)
                logger.info(f"Got {len(cookies)} IEEE cookies via FlareSolverr")

        # Get paper list from IEEE Xplore API
        papers = self._get_papers_from_xplore_api(year)

        if not papers:
            logger.warning(f"No papers found for {year}")
            return []

        logger.info(f"Found {len(papers)} papers for {year}")
        return papers

    def get_pdf_urls(self, paper: PaperInfo) -> List[str]:
        """
        Get PDF URLs to try for a paper

        Args:
            paper: Paper information

        Returns:
            List of URLs to try
        """
        urls = []

        # Get article info from extra fields
        article_number = paper.extra.get('article_number', '')
        publication_number = paper.extra.get('publication_number', '')
        is_number = paper.extra.get('is_number', '')

        # 1. Direct ielx PDF URLs (most reliable)
        if article_number and is_number and publication_number:
            urls.append(
                f"{self.XPLORE_BASE}/ielx7/{publication_number}/{is_number}/"
                f"{article_number}.pdf?tp=&arnumber={article_number}&isnumber={is_number}&ref="
            )
            urls.append(
                f"{self.XPLORE_BASE}/ielx8/{publication_number}/{is_number}/"
                f"{article_number}.pdf?tp=&arnumber={article_number}&isnumber={is_number}&ref="
            )

        # 2. Original pdf_url
        if paper.pdf_url and paper.pdf_url not in urls:
            urls.append(paper.pdf_url)

        # 3. Try Semantic Scholar / arXiv
        pdf_url, source = self.semantic_scholar.find_open_access_pdf(
            doi=paper.doi,
            title=paper.title
        )
        if pdf_url:
            urls.append(pdf_url)
            logger.debug(f"Found open access PDF via {source}")

        # 4. Try arXiv directly
        if not pdf_url:
            arxiv_url, _ = self.arxiv.find_paper(title=paper.title)
            if arxiv_url:
                urls.append(arxiv_url)
                logger.debug(f"Found arXiv PDF")

        return urls

    def _get_papers_from_xplore_api(self, year: int) -> List[PaperInfo]:
        """
        Get papers from IEEE Xplore REST API

        Args:
            year: Conference year

        Returns:
            List of PaperInfo objects
        """
        papers = []

        punumber = self.YEAR_PROCEEDING_IDS.get(year)
        if not punumber:
            logger.warning(f"Unknown proceeding ID for {year}, trying search...")
            return self._search_papers_by_year(year)

        logger.info(f"Fetching from IEEE Xplore API (punumber={punumber})...")

        session = self.session_manager.create_session()
        api_url = f"{self.XPLORE_BASE}/rest/search"

        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Origin': self.XPLORE_BASE,
            'Referer': f'{self.XPLORE_BASE}/xpl/conhome/{punumber}/proceeding',
        }

        page = 1
        rows_per_page = 100

        while True:
            payload = {
                'punumber': punumber,
                'rowsPerPage': rows_per_page,
                'pageNumber': page,
            }

            try:
                response = session.post(api_url, json=payload, headers=headers, timeout=60)

                if response.status_code != 200:
                    logger.warning(f"IEEE Xplore API returned {response.status_code}")
                    break

                data = response.json()
                total_records = data.get('totalRecords', 0)
                records = data.get('records', [])

                if page == 1:
                    logger.info(f"IEEE Xplore API returned {total_records} papers")

                if not records:
                    break

                for record in records:
                    title = record.get('articleTitle', '')
                    if not title:
                        continue

                    article_number = record.get('articleNumber', '')
                    publication_number = record.get('publicationNumber', '') or punumber
                    is_number = record.get('isNumber', '')

                    # Extract authors
                    authors = []
                    for author in record.get('authors', []):
                        name = author.get('preferredName', '') or author.get('normalizedName', '')
                        if name:
                            authors.append(name)

                    # Build direct PDF URL
                    pdf_url = ''
                    if article_number and is_number:
                        pdf_url = (
                            f"{self.XPLORE_BASE}/ielx7/{publication_number}/{is_number}/"
                            f"{article_number}.pdf?tp=&arnumber={article_number}&isnumber={is_number}&ref="
                        )

                    papers.append(PaperInfo(
                        title=title,
                        authors=', '.join(authors),
                        pdf_url=pdf_url,
                        doi=record.get('doi', ''),
                        abstract=record.get('abstract', ''),
                        source='IEEE',
                        extra={
                            'article_number': article_number,
                            'publication_number': publication_number,
                            'is_number': is_number,
                            'is_open_access': record.get('isOpenAccess', False),
                        }
                    ))

                if len(papers) >= total_records or len(records) < rows_per_page:
                    break

                page += 1
                time.sleep(self.delay)

            except Exception as e:
                logger.error(f"IEEE Xplore API request failed: {e}")
                break

        session.close()
        return papers

    def _search_papers_by_year(self, year: int) -> List[PaperInfo]:
        """
        Search for papers by year

        Args:
            year: Conference year

        Returns:
            List of PaperInfo objects
        """
        papers = []
        session = self.session_manager.create_session()

        api_url = f"{self.XPLORE_BASE}/rest/search"
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Origin': self.XPLORE_BASE,
        }

        search_query = f'"IEEE Symposium on Security and Privacy" AND year:{year}'
        payload = {
            'queryText': search_query,
            'rowsPerPage': 100,
            'pageNumber': 1,
        }

        try:
            response = session.post(api_url, json=payload, headers=headers, timeout=60)

            if response.status_code == 200:
                data = response.json()
                records = data.get('records', [])

                for record in records:
                    title = record.get('articleTitle', '')
                    if not title:
                        continue

                    article_number = record.get('articleNumber', '')
                    authors = []
                    for author in record.get('authors', []):
                        name = author.get('preferredName', '') or author.get('normalizedName', '')
                        if name:
                            authors.append(name)

                    pdf_url = ''
                    if article_number:
                        pdf_url = f"{self.XPLORE_BASE}/stamp/stamp.jsp?tp=&arnumber={article_number}"

                    papers.append(PaperInfo(
                        title=title,
                        authors=', '.join(authors),
                        pdf_url=pdf_url,
                        doi=record.get('doi', ''),
                        abstract=record.get('abstract', ''),
                        source='IEEE',
                        extra={
                            'article_number': article_number,
                            'is_open_access': record.get('isOpenAccess', False),
                        }
                    ))

        except Exception as e:
            logger.error(f"Search failed: {e}")

        session.close()
        return papers
