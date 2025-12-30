"""
Browser-based PDF downloader for bypassing Cloudflare

Uses Playwright to download PDFs from protected sites like ACM DL.
"""

import logging
import time
from pathlib import Path
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class BrowserPDFDownloader:
    """Download PDFs using a real browser to bypass Cloudflare"""

    def __init__(
        self,
        headless: bool = True,
        max_workers: int = 2,
        proxy: Optional[str] = None,
    ):
        """
        Initialize browser PDF downloader

        Args:
            headless: Run browser in headless mode
            max_workers: Maximum concurrent browser instances
            proxy: Optional proxy server (e.g., "socks5://127.0.0.1:1080")
        """
        self.headless = headless
        self.max_workers = max_workers
        self.proxy = proxy

    def download_pdf(
        self,
        paper_url: str,
        pdf_url: str,
        save_path: Path,
        timeout: int = 60,
    ) -> bool:
        """
        Download a single PDF using browser

        Args:
            paper_url: URL of the paper page (for session establishment)
            pdf_url: Direct PDF URL
            save_path: Path to save the PDF
            timeout: Download timeout in seconds

        Returns:
            True if download successful
        """
        # Skip if already exists
        if save_path.exists() and save_path.stat().st_size > 50000:
            logger.debug(f"Already exists: {save_path.name}")
            return True

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                # Configure proxy if provided
                launch_options = {"headless": self.headless}
                if self.proxy:
                    launch_options["proxy"] = {"server": self.proxy}

                browser = p.firefox.launch(**launch_options)

                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
                        "Gecko/20100101 Firefox/128.0"
                    ),
                    accept_downloads=True,
                )

                page = context.new_page()

                # Visit paper page first to establish session
                logger.debug(f"Visiting paper page: {paper_url[:50]}...")
                page.goto(paper_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(1)

                # Download PDF
                logger.debug(f"Downloading PDF: {pdf_url[:50]}...")
                save_path.parent.mkdir(parents=True, exist_ok=True)

                with page.expect_download(timeout=timeout * 1000) as download_info:
                    page.evaluate(f'window.location.href = "{pdf_url}"')

                download = download_info.value
                download.save_as(str(save_path))

                browser.close()

                # Validate
                if save_path.exists():
                    size = save_path.stat().st_size
                    if size > 50000:
                        with open(save_path, 'rb') as f:
                            if f.read(4) == b'%PDF':
                                logger.info(f"✓ Downloaded: {save_path.name} ({size:,} bytes)")
                                return True
                            else:
                                logger.warning(f"Invalid PDF: {save_path.name}")
                                save_path.unlink()
                    else:
                        logger.warning(f"File too small: {save_path.name} ({size} bytes)")
                        save_path.unlink()

                return False

        except ImportError:
            logger.error("Playwright not installed")
            return False
        except Exception as e:
            logger.error(f"Download failed: {e}")
            if save_path.exists():
                save_path.unlink()
            return False

    def download_acm_paper(
        self,
        doi: str,
        save_path: Path,
        timeout: int = 60,
        max_retries: int = 2,
    ) -> bool:
        """
        Download an ACM paper by DOI

        Args:
            doi: Paper DOI (e.g., "10.1145/3372297.3423349")
            save_path: Path to save the PDF
            timeout: Download timeout in seconds
            max_retries: Maximum number of retry attempts

        Returns:
            True if download successful
        """
        paper_url = f"https://dl.acm.org/doi/{doi}"
        pdf_url = f"https://dl.acm.org/doi/pdf/{doi}"

        for attempt in range(max_retries + 1):
            if self.download_pdf(paper_url, pdf_url, save_path, timeout):
                return True
            if attempt < max_retries:
                wait_time = (attempt + 1) * 5
                logger.debug(f"Retry {attempt + 1}/{max_retries}, waiting {wait_time}s...")
                time.sleep(wait_time)
        return False

    def download_ieee_paper(
        self,
        article_number: str,
        save_path: Path,
        timeout: int = 60,
        max_retries: int = 2,
    ) -> bool:
        """
        Download an IEEE paper by article number using stamp.jsp

        Args:
            article_number: IEEE article number (e.g., "9519428")
            save_path: Path to save the PDF
            timeout: Download timeout in seconds
            max_retries: Maximum number of retry attempts

        Returns:
            True if download successful
        """
        # IEEE stamp.jsp is the gateway to PDF downloads
        stamp_url = f"https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber={article_number}"

        for attempt in range(max_retries + 1):
            if self._download_ieee_via_stamp(stamp_url, save_path, timeout):
                return True
            if attempt < max_retries:
                wait_time = (attempt + 1) * 5
                logger.debug(f"Retry {attempt + 1}/{max_retries}, waiting {wait_time}s...")
                time.sleep(wait_time)
        return False

    def _download_ieee_via_stamp(
        self,
        stamp_url: str,
        save_path: Path,
        timeout: int = 60,
        context=None,
        page=None,
    ) -> bool:
        """
        Download IEEE paper via stamp.jsp page

        The stamp.jsp page contains an iframe with getPDF.jsp that serves the PDF.
        """
        if save_path.exists() and save_path.stat().st_size > 50000:
            logger.debug(f"Already exists: {save_path.name}")
            return True

        own_browser = False
        browser = None

        try:
            from playwright.sync_api import sync_playwright

            # Reuse context/page if provided, otherwise create new
            if context is None:
                own_browser = True
                p = sync_playwright().start()
                browser = p.firefox.launch(headless=self.headless)
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
                        "Gecko/20100101 Firefox/128.0"
                    ),
                    accept_downloads=True,
                )
                page = context.new_page()

            save_path.parent.mkdir(parents=True, exist_ok=True)

            # Visit stamp.jsp page - use domcontentloaded for speed
            logger.debug(f"Visiting stamp page: {stamp_url}")
            page.goto(stamp_url, wait_until="domcontentloaded", timeout=30000)

            # Wait a bit for iframe to load
            time.sleep(1)

            # Find the getPDF.jsp iframe
            pdf_url = None
            for _ in range(5):  # Retry a few times
                iframes = page.query_selector_all("iframe")
                for iframe in iframes:
                    src = iframe.get_attribute("src")
                    if src and "getPDF.jsp" in src:
                        pdf_url = src
                        break
                if pdf_url:
                    break
                time.sleep(0.5)

            if not pdf_url:
                logger.debug("Could not find getPDF.jsp iframe")
                if own_browser and browser:
                    browser.close()
                return False

            logger.debug(f"Found PDF URL: {pdf_url[:80]}...")

            # Navigate directly to the PDF iframe URL
            try:
                with page.expect_download(timeout=timeout * 1000) as download_info:
                    page.evaluate(f'window.location.href = "{pdf_url}"')

                download = download_info.value
                download.save_as(str(save_path))
            except Exception as e:
                logger.debug(f"expect_download failed: {e}")
                if own_browser and browser:
                    browser.close()
                return False

            if own_browser and browser:
                browser.close()

            # Validate
            if save_path.exists():
                size = save_path.stat().st_size
                if size > 50000:
                    with open(save_path, 'rb') as f:
                        if f.read(4) == b'%PDF':
                            logger.info(f"✓ Downloaded: {save_path.name} ({size:,} bytes)")
                            return True
                        else:
                            logger.warning(f"Invalid PDF: {save_path.name}")
                            save_path.unlink()
                else:
                    logger.warning(f"File too small: {save_path.name} ({size} bytes)")
                    save_path.unlink()

            return False

        except ImportError:
            logger.error("Playwright not installed")
            return False
        except Exception as e:
            logger.error(f"Download failed: {e}")
            if save_path.exists():
                save_path.unlink()
            if own_browser and browser:
                try:
                    browser.close()
                except Exception:
                    pass
            return False

    def download_batch(
        self,
        papers: List[dict],
        save_dir: Path,
        delay: float = 3.0,
    ) -> tuple:
        """
        Download multiple papers

        Args:
            papers: List of dicts with 'doi' and 'title' keys
            save_dir: Directory to save PDFs
            delay: Delay between downloads in seconds

        Returns:
            Tuple of (success_count, total_count)
        """
        from ..core.utils import sanitize_filename

        save_dir.mkdir(parents=True, exist_ok=True)
        success_count = 0
        total = len(papers)

        for i, paper in enumerate(papers, 1):
            doi = paper.get('doi', '')
            title = paper.get('title', '')

            if not doi:
                logger.warning(f"[{i}/{total}] No DOI: {title[:50]}")
                continue

            filename = sanitize_filename(title) + '.pdf'
            save_path = save_dir / filename

            # Skip if exists
            if save_path.exists() and save_path.stat().st_size > 50000:
                logger.info(f"[{i}/{total}] Skipped (exists): {filename[:50]}")
                success_count += 1
                continue

            logger.info(f"[{i}/{total}] Downloading: {title[:50]}...")

            if self.download_acm_paper(doi, save_path):
                success_count += 1
            else:
                logger.error(f"[{i}/{total}] Failed: {title[:50]}")

            time.sleep(delay)

        logger.info(f"Batch complete: {success_count}/{total} succeeded")
        return success_count, total


def download_acm_ccs_missing(
    year: int,
    headless: bool = True,
    proxy: Optional[str] = None,
) -> tuple:
    """
    Download missing ACM CCS papers for a specific year

    Args:
        year: Conference year
        headless: Run browser in headless mode
        proxy: Optional SOCKS5 proxy (e.g., "socks5://127.0.0.1:1080")

    Returns:
        Tuple of (success_count, total_missing)
    """
    import csv
    from pathlib import Path
    from playwright.sync_api import sync_playwright

    base_dir = Path(__file__).parent.parent.parent.parent.parent
    meta_file = base_dir / f"ACM_CCS/{year}/metadata.csv"
    papers_dir = base_dir / f"ACM_CCS/{year}/papers"

    if not meta_file.exists():
        logger.error(f"Metadata file not found: {meta_file}")
        return 0, 0

    # Read metadata
    papers = []
    with open(meta_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            papers.append(row)

    # Find missing papers
    from ..core.utils import sanitize_filename

    missing = []
    for paper in papers:
        title = paper.get('Title') or paper.get('title') or ''
        doi = paper.get('DOI') or paper.get('doi') or ''

        if not doi or not title:
            continue

        # Skip workshop papers
        if 'workshop' in title.lower() or "'" in title[:10]:
            continue

        filename = sanitize_filename(title) + '.pdf'
        save_path = papers_dir / filename

        if not save_path.exists() or save_path.stat().st_size < 50000:
            missing.append({'doi': doi, 'title': title})

    if not missing:
        logger.info(f"No missing papers for {year}")
        return 0, 0

    logger.info(f"Found {len(missing)} missing papers for {year}")

    # Download missing papers with browser reuse for speed
    papers_dir.mkdir(parents=True, exist_ok=True)

    success_count = 0
    total = len(missing)

    # Configure browser launch options
    launch_options = {"headless": headless}
    if proxy:
        launch_options["proxy"] = {"server": proxy}
        logger.info(f"Using proxy: {proxy}")

    # Use a single browser instance for all downloads
    with sync_playwright() as p:
        browser = p.firefox.launch(**launch_options)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
                "Gecko/20100101 Firefox/128.0"
            ),
            accept_downloads=True,
        )
        page = context.new_page()

        for i, paper in enumerate(missing, 1):
            doi = paper['doi']
            title = paper['title']
            filename = sanitize_filename(title) + '.pdf'
            save_path = papers_dir / filename

            # Skip if already exists
            if save_path.exists() and save_path.stat().st_size > 50000:
                logger.info(f"[{i}/{total}] Skipped (exists): {filename[:50]}")
                success_count += 1
                continue

            logger.info(f"[{i}/{total}] Downloading: {title[:50]}...")

            paper_url = f"https://dl.acm.org/doi/{doi}"
            pdf_url = f"https://dl.acm.org/doi/pdf/{doi}"

            # Try up to 3 times for each paper
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Visit paper page first to establish session
                    # Use longer timeout for proxy connections
                    page.goto(paper_url, wait_until="domcontentloaded", timeout=60000)
                    time.sleep(1)

                    # Download PDF
                    save_path.parent.mkdir(parents=True, exist_ok=True)

                    with page.expect_download(timeout=90000) as download_info:
                        page.evaluate(f'window.location.href = "{pdf_url}"')

                    download = download_info.value
                    download.save_as(str(save_path))

                    # Validate
                    if save_path.exists():
                        size = save_path.stat().st_size
                        if size > 50000:
                            with open(save_path, 'rb') as f:
                                if f.read(4) == b'%PDF':
                                    logger.info(f"✓ Downloaded: {save_path.name} ({size:,} bytes)")
                                    success_count += 1
                                    break  # Success, exit retry loop
                                else:
                                    logger.warning(f"Invalid PDF: {save_path.name}")
                                    save_path.unlink()
                        else:
                            logger.warning(f"File too small: {save_path.name} ({size} bytes)")
                            save_path.unlink()

                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.debug(f"[{i}/{total}] Attempt {attempt + 1} failed: {e}")
                        time.sleep(2)  # Wait before retry
                    else:
                        logger.error(f"[{i}/{total}] Failed after {max_retries} attempts: {e}")
                    if save_path.exists():
                        save_path.unlink()

            time.sleep(1)  # Short delay between downloads

        browser.close()

    logger.info(f"ACM CCS {year} complete: {success_count}/{total} succeeded")
    return success_count, total


def download_ieee_sp_missing(year: int, headless: bool = True) -> tuple:
    """
    Download missing IEEE S&P papers for a specific year

    Args:
        year: Conference year
        headless: Run browser in headless mode

    Returns:
        Tuple of (success_count, total_missing)
    """
    import csv
    from pathlib import Path

    base_dir = Path(__file__).parent.parent.parent.parent.parent
    meta_file = base_dir / f"IEEE_SP/{year}/metadata.csv"
    papers_dir = base_dir / f"IEEE_SP/{year}/papers"

    if not meta_file.exists():
        logger.error(f"Metadata file not found: {meta_file}")
        return 0, 0

    # Read metadata
    from ..core.utils import sanitize_filename

    papers = []
    with open(meta_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            papers.append(row)

    # Find missing papers
    missing = []
    for paper in papers:
        title = paper.get('title', '')
        article_number = paper.get('article_number', '')

        if not article_number or not title:
            continue

        filename = sanitize_filename(title) + '.pdf'
        save_path = papers_dir / filename

        if not save_path.exists() or save_path.stat().st_size < 50000:
            missing.append({
                'article_number': article_number,
                'title': title,
            })

    if not missing:
        logger.info(f"No missing papers for IEEE S&P {year}")
        return 0, 0

    logger.info(f"Found {len(missing)} missing papers for IEEE S&P {year}")

    # Download missing papers with browser reuse for speed
    from playwright.sync_api import sync_playwright

    papers_dir.mkdir(parents=True, exist_ok=True)
    downloader = BrowserPDFDownloader(headless=headless)

    success_count = 0
    total = len(missing)

    # Use a single browser instance for all downloads
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
                "Gecko/20100101 Firefox/128.0"
            ),
            accept_downloads=True,
        )
        page = context.new_page()

        for i, paper in enumerate(missing, 1):
            article_number = paper['article_number']
            title = paper['title']
            filename = sanitize_filename(title) + '.pdf'
            save_path = papers_dir / filename

            logger.info(f"[{i}/{total}] Downloading: {title[:50]}...")

            # Use the shared context and page
            stamp_url = f"https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber={article_number}"
            if downloader._download_ieee_via_stamp(stamp_url, save_path, timeout=60, context=context, page=page):
                success_count += 1
            else:
                logger.error(f"[{i}/{total}] Failed: {title[:50]}")

            time.sleep(1)  # Short delay between downloads

        browser.close()

    logger.info(f"IEEE S&P {year} complete: {success_count}/{total} succeeded")
    return success_count, total


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2020
    headless = "--no-headless" not in sys.argv

    success, total = download_acm_ccs_missing(year, headless=headless)
    print(f"\nResult: {success}/{total} papers downloaded")
