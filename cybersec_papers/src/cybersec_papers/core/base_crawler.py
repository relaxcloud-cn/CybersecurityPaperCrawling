"""
Base crawler class with common functionality
"""

import logging
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import List, Optional, Dict, Any
import time

from .downloader import PDFDownloader
from .metadata import MetadataManager
from .session import SessionManager
from .utils import sanitize_filename, ensure_dir
from ..config import DEFAULT_DELAY, DEFAULT_WORKERS, DEFAULT_METADATA_FORMAT

logger = logging.getLogger(__name__)


@dataclass
class PaperInfo:
    """Paper information container"""
    title: str
    authors: str = ""
    pdf_url: str = ""
    doi: str = ""
    abstract: str = ""
    source: str = ""
    # Additional fields can be stored here
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        result = {
            'title': self.title,
            'authors': self.authors,
            'pdf_url': self.pdf_url,
            'doi': self.doi,
            'abstract': self.abstract,
            'source': self.source,
        }
        result.update(self.extra)
        return result


class BaseCrawler(ABC):
    """
    Abstract base class for conference paper crawlers

    Subclasses must implement:
    - get_paper_list(year) -> List[PaperInfo]
    - get_pdf_urls(paper) -> List[str]
    """

    def __init__(
        self,
        conference: str,
        conference_dir: str,
        base_dir: Path,
        delay: float = DEFAULT_DELAY,
        max_workers: int = DEFAULT_WORKERS,
        metadata_format: str = DEFAULT_METADATA_FORMAT,
    ):
        """
        Initialize crawler

        Args:
            conference: Conference name for display
            conference_dir: Directory name for data storage
            base_dir: Base directory for data storage
            delay: Delay between requests in seconds
            max_workers: Maximum concurrent download threads
            metadata_format: Format for metadata files ('csv', 'json', 'txt', 'all')
        """
        self.conference = conference
        self.conference_dir = conference_dir
        self.base_dir = Path(base_dir)
        self.delay = delay
        self.max_workers = max_workers
        self.metadata_format = metadata_format

        # Components
        self.session_manager = SessionManager()
        self.downloader = PDFDownloader()
        self.metadata_manager = MetadataManager(base_dir, conference_dir)

        # Counters (thread-safe)
        self._lock = Lock()
        self._downloaded_count = 0
        self._skipped_count = 0
        self._failed_count = 0

    @abstractmethod
    def get_paper_list(self, year: int) -> List[PaperInfo]:
        """
        Get list of papers for a specific year

        Args:
            year: Conference year

        Returns:
            List of PaperInfo objects
        """
        pass

    def get_pdf_urls(self, paper: PaperInfo) -> List[str]:
        """
        Get PDF URLs to try for a paper

        Default implementation returns paper.pdf_url as single-item list.
        Override for multiple URL fallbacks.

        Args:
            paper: Paper information

        Returns:
            List of URLs to try
        """
        if paper.pdf_url:
            return [paper.pdf_url]
        return []

    def crawl_year(self, year: int) -> int:
        """
        Crawl papers for a specific year

        Args:
            year: Conference year

        Returns:
            Number of papers downloaded
        """
        logger.info(f"Starting crawl for {self.conference} {year}")

        # Get paper list
        papers = self.get_paper_list(year)
        if not papers:
            logger.warning(f"No papers found for {year}")
            return 0

        logger.info(f"Found {len(papers)} papers")

        # Prepare output directory
        papers_dir = ensure_dir(self.base_dir / self.conference_dir / str(year) / 'papers')

        # Reset counters
        self._downloaded_count = 0
        self._skipped_count = 0
        self._failed_count = 0

        # Prepare download tasks
        tasks = []
        for i, paper in enumerate(papers, 1):
            filename = sanitize_filename(paper.title) + '.pdf'
            save_path = papers_dir / filename
            tasks.append((paper, save_path, i, len(papers)))

        # Execute downloads
        if self.max_workers == 1:
            for task in tasks:
                self._download_worker(task)
                time.sleep(self.delay)
        else:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(self._download_worker, task): task
                    for task in tasks
                }
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        logger.error(f"Task error: {e}")
                    time.sleep(self.delay)

        # Save metadata
        paper_dicts = [p.to_dict() for p in papers]
        formats = ['all'] if self.metadata_format == 'all' else [self.metadata_format]
        self.metadata_manager.save(paper_dicts, year, formats)

        # Log summary
        logger.info(
            f"{year} complete: "
            f"downloaded {self._downloaded_count}, "
            f"skipped {self._skipped_count}, "
            f"failed {self._failed_count}, "
            f"total {len(papers)}"
        )

        return self._downloaded_count + self._skipped_count

    def _download_worker(self, task: tuple) -> bool:
        """
        Worker function for downloading a single paper

        Args:
            task: (paper, save_path, index, total)

        Returns:
            True if download successful
        """
        paper, save_path, index, total = task

        # Check if already exists
        if save_path.exists() and save_path.stat().st_size > 50000:
            with self._lock:
                self._skipped_count += 1
            logger.info(f"[{index}/{total}] Skipped (exists): {save_path.name[:60]}")
            return True

        logger.info(f"[{index}/{total}] Downloading: {paper.title[:60]}...")

        # Get URLs to try
        urls = self.get_pdf_urls(paper)
        if not urls:
            with self._lock:
                self._failed_count += 1
            logger.error(f"[{index}/{total}] No PDF URL: {paper.title[:50]}")
            return False

        # Create worker session
        session = self.session_manager.create_worker_session()

        # Try to download
        success = self.downloader.download(urls, save_path, session)

        with self._lock:
            if success:
                self._downloaded_count += 1
                logger.info(f"[{index}/{total}] Downloaded: {save_path.name[:60]}")
            else:
                self._failed_count += 1
                logger.error(f"[{index}/{total}] Failed: {paper.title[:50]}")

        session.close()
        return success

    def crawl(self, years: Optional[List[int]] = None) -> int:
        """
        Crawl papers for multiple years

        Args:
            years: List of years to crawl

        Returns:
            Total number of papers downloaded
        """
        if years is None:
            from ..config import CONFERENCES
            # Find config by matching conference_dir
            for conf in CONFERENCES.values():
                if conf.dir_name == self.conference_dir:
                    years = conf.years
                    break
            if years is None:
                years = [2023, 2022, 2021, 2020]

        logger.info(f"Starting {self.conference} crawl for years: {years}")
        logger.info("=" * 60)

        total_downloaded = 0
        for year in years:
            try:
                time.sleep(self.delay)
                count = self.crawl_year(year)
                total_downloaded += count
            except Exception as e:
                logger.error(f"Failed to crawl {year}: {e}")
                import traceback
                logger.debug(traceback.format_exc())

        logger.info(f"Crawl complete! Total: {total_downloaded} papers")
        return total_downloaded
