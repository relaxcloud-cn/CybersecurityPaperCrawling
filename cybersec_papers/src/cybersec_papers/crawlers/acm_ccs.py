"""
ACM CCS (ACM Conference on Computer and Communications Security) paper crawler
"""

import logging
import re
import time
from pathlib import Path
from typing import List, Optional

from bs4 import BeautifulSoup

from ..core.base_crawler import BaseCrawler, PaperInfo
from ..config import DATA_DIR
from ..services import FlareSolverrClient, SemanticScholarClient, ArxivClient

logger = logging.getLogger(__name__)


class ACMCCSCrawler(BaseCrawler):
    """ACM CCS paper crawler - hybrid strategy (FlareSolverr + open access)"""

    DBLP_BASE = "https://dblp.org"
    ACM_DL_BASE = "https://dl.acm.org"
    SIGSAC_BASE = "https://www.sigsac.org"

    # CCS proceedings DOI prefixes
    CCS_DOI_PREFIXES = {
        2024: "10.1145/3658644",
        2023: "10.1145/3576915",
        2022: "10.1145/3548606",
        2021: "10.1145/3460120",
        2020: "10.1145/3372297",
        2019: "10.1145/3319535",
        2018: "10.1145/3243734",
    }

    def __init__(
        self,
        base_dir: Path = None,
        delay: float = 1.0,
        max_workers: int = 3,
        metadata_format: str = 'csv',
        cookies_file: str = None,
    ):
        """
        Initialize crawler

        Args:
            base_dir: Base directory for data storage
            delay: Delay between requests in seconds
            max_workers: Maximum concurrent download threads
            metadata_format: Format for metadata files
            cookies_file: Path to saved ACM cookies file
        """
        if base_dir is None:
            base_dir = DATA_DIR

        super().__init__(
            conference="ACM CCS",
            conference_dir="ACM_CCS",
            base_dir=base_dir,
            delay=delay,
            max_workers=max_workers,
            metadata_format=metadata_format,
        )

        self.flaresolverr = FlareSolverrClient()
        self.semantic_scholar = SemanticScholarClient()
        self.arxiv = ArxivClient()
        self.acm_cookies = None
        self.cookies_file = cookies_file

    def get_paper_list(self, year: int) -> List[PaperInfo]:
        """
        Get list of papers for a specific year

        Args:
            year: Conference year

        Returns:
            List of PaperInfo objects
        """
        logger.info(f"Fetching paper list for ACM CCS {year}")

        # Try to load cookies
        if self.cookies_file:
            self._load_cookies_from_file()

        # Get paper list from DBLP
        papers = self._get_papers_from_dblp(year)

        if not papers:
            # Fallback: OpenTOC
            papers = self._get_papers_from_opentoc(year)

        if not papers:
            logger.warning(f"No papers found for {year}")
            return []

        # Try to get ACM cookies via FlareSolverr
        if not self.acm_cookies and self.flaresolverr.check_available():
            sample_doi = None
            for paper in papers:
                if paper.doi:
                    sample_doi = paper.doi
                    break

            if sample_doi:
                logger.info("Getting ACM cookies via FlareSolverr...")
                cookies, _ = self.flaresolverr.get_cookies(
                    f"{self.ACM_DL_BASE}/doi/pdf/{sample_doi}"
                )
                if cookies:
                    self.acm_cookies = cookies
                    self.session_manager.update_cookies(cookies)
                    self._save_cookies_to_file(cookies)
                    logger.info(f"Got {len(cookies)} ACM cookies")

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

        # 1. ACM DL URL (if we have cookies)
        if paper.doi and self.acm_cookies:
            urls.append(f"{self.ACM_DL_BASE}/doi/pdf/{paper.doi}")

        # 2. Existing pdf_url
        if paper.pdf_url:
            urls.append(paper.pdf_url)

        # 3. Try Semantic Scholar / arXiv
        pdf_url, source = self.semantic_scholar.find_open_access_pdf(
            doi=paper.doi,
            title=paper.title
        )
        if pdf_url and pdf_url not in urls:
            urls.append(pdf_url)
            logger.debug(f"Found open access PDF via {source}")

        # 4. Try arXiv directly
        arxiv_url, _ = self.arxiv.find_paper(title=paper.title)
        if arxiv_url and arxiv_url not in urls:
            urls.append(arxiv_url)
            logger.debug(f"Found arXiv PDF")

        return urls

    def _get_papers_from_dblp(self, year: int) -> List[PaperInfo]:
        """
        Get papers from DBLP

        Args:
            year: Conference year

        Returns:
            List of PaperInfo objects
        """
        papers = []
        url = f"{self.DBLP_BASE}/db/conf/ccs/ccs{year}.html"
        session = self.session_manager.create_session()

        try:
            logger.info(f"Fetching paper list from DBLP: {url}")
            response = session.get(url, timeout=30)

            if response.status_code != 200:
                logger.warning(f"DBLP returned {response.status_code}")
                return papers

            soup = BeautifulSoup(response.text, 'html.parser')
            entries = soup.find_all('li', class_='entry')
            logger.info(f"Found {len(entries)} entries")

            for entry in entries:
                # Skip proceedings entries
                if 'proceedings' in entry.get('class', []):
                    continue

                # Extract title
                title_elem = entry.find('span', class_='title')
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                if title.endswith('.'):
                    title = title[:-1]

                # Extract DOI
                doi = ''
                doi_link = entry.find('a', href=lambda x: x and 'doi.org' in x)
                if doi_link:
                    href = doi_link.get('href', '')
                    doi_match = re.search(r'doi\.org/(10\.\d+/[^\s]+)', href)
                    if doi_match:
                        doi = doi_match.group(1)

                # Extract authors
                authors = []
                author_spans = entry.find_all('span', itemprop='author')
                for author_span in author_spans:
                    name = author_span.get_text(strip=True)
                    if name:
                        authors.append(name)

                papers.append(PaperInfo(
                    title=title,
                    authors=', '.join(authors),
                    doi=doi,
                    pdf_url='',
                    source='',
                ))

            logger.info(f"Got {len(papers)} papers from DBLP")

        except Exception as e:
            logger.error(f"Failed to get paper list from DBLP: {e}")
        finally:
            session.close()

        return papers

    def _get_papers_from_opentoc(self, year: int) -> List[PaperInfo]:
        """
        Get papers from SIGSAC OpenTOC

        Args:
            year: Conference year

        Returns:
            List of PaperInfo objects
        """
        papers = []
        session = self.session_manager.create_session()

        urls = [
            f"{self.SIGSAC_BASE}/ccs/CCS{year}/tocs/tocs-ccs{year % 100}.html",
            f"{self.SIGSAC_BASE}/ccs/CCS{year}/tocs/tocs-ccs{year}.html",
        ]

        for url in urls:
            try:
                logger.info(f"Trying OpenTOC: {url}")
                response = session.get(url, timeout=30)

                if response.status_code != 200:
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')
                paper_links = soup.find_all('a', href=lambda x: x and 'dl.acm.org/doi/10.1145' in x)

                for link in paper_links:
                    href = link.get('href', '')
                    title = link.get_text(strip=True)

                    if not title or len(title) < 10:
                        continue

                    # Extract DOI
                    doi_match = re.search(r'10\.1145/[\d.]+', href)
                    doi = doi_match.group(0) if doi_match else ''

                    # Extract authors
                    authors = ''
                    parent = link.find_parent(['div', 'li', 'h5'])
                    if parent:
                        next_elem = parent.find_next_sibling(['ul', 'div'])
                        if next_elem:
                            author_items = next_elem.find_all('li')
                            authors = ', '.join([a.get_text(strip=True) for a in author_items])

                    papers.append(PaperInfo(
                        title=title,
                        authors=authors,
                        doi=doi,
                        pdf_url='',
                        source='',
                    ))

                if papers:
                    logger.info(f"Got {len(papers)} papers from OpenTOC")
                    break

            except Exception as e:
                logger.debug(f"OpenTOC access failed: {e}")
                continue

        session.close()
        return papers

    def _load_cookies_from_file(self):
        """Load cookies from file"""
        if self.cookies_file and Path(self.cookies_file).exists():
            try:
                import json
                with open(self.cookies_file, 'r') as f:
                    cookies = json.load(f)
                self.acm_cookies = cookies
                self.session_manager.update_cookies(cookies)
                logger.info(f"Loaded {len(cookies)} cookies from file")
            except Exception as e:
                logger.warning(f"Failed to load cookies: {e}")

    def _save_cookies_to_file(self, cookies: list):
        """Save cookies to file"""
        cookies_path = self.base_dir / self.conference_dir / "acm_cookies.json"
        try:
            import json
            cookies_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cookies_path, 'w') as f:
                json.dump(cookies, f, indent=2)
            logger.info(f"Cookies saved to {cookies_path}")
        except Exception as e:
            logger.warning(f"Failed to save cookies: {e}")
