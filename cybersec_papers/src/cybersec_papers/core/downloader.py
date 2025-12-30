"""
PDF downloader with retry logic and validation
"""

import time
import logging
from pathlib import Path
from typing import Optional, List

import requests

from ..config import MIN_PDF_SIZE

logger = logging.getLogger(__name__)


class PDFDownloader:
    """Downloads PDF files with retry logic and validation"""

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        """
        Initialize downloader

        Args:
            max_retries: Maximum retry attempts per URL
            retry_delay: Initial delay between retries (exponential backoff)
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def download(
        self,
        urls: List[str],
        save_path: Path,
        session: Optional[requests.Session] = None,
    ) -> bool:
        """
        Download PDF from a list of URLs (tries each until success)

        Args:
            urls: List of URLs to try
            save_path: Path to save the PDF
            session: Optional requests session to use

        Returns:
            True if download successful
        """
        # Skip if file already exists and is valid
        if save_path.exists() and save_path.stat().st_size > MIN_PDF_SIZE:
            return True

        if session is None:
            session = requests.Session()

        for url in urls:
            if self._download_single(url, save_path, session):
                return True

        return False

    def _download_single(
        self,
        url: str,
        save_path: Path,
        session: requests.Session,
    ) -> bool:
        """
        Download from a single URL with retries

        Args:
            url: URL to download from
            save_path: Path to save the PDF
            session: Requests session to use

        Returns:
            True if download successful
        """
        for attempt in range(self.max_retries):
            temp_path = save_path.with_suffix('.tmp')

            try:
                if attempt > 0:
                    wait_time = min(self.retry_delay * (2 ** (attempt - 1)), 5)
                    logger.debug(f"Retry {attempt + 1}/{self.max_retries}, waiting {wait_time}s")
                    time.sleep(wait_time)

                response = session.get(
                    url,
                    timeout=(10, 60),  # 连接10秒，读取60秒超时
                    stream=True,
                    allow_redirects=True,
                )

                # Check for auth/access errors
                if response.status_code in [401, 403]:
                    logger.debug(f"Access denied for {url}")
                    return False

                if response.status_code == 404:
                    logger.debug(f"Not found: {url}")
                    return False

                response.raise_for_status()

                # Download and validate
                total_size = 0
                first_chunk = None
                is_html = False

                with open(temp_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            if first_chunk is None:
                                first_chunk = chunk

                                # Check if it's a PDF
                                if chunk[:4] != b'%PDF':
                                    preview = chunk[:500].decode('utf-8', errors='ignore').lower()
                                    if '<html' in preview or '<!doctype' in preview:
                                        if any(x in preview for x in ['login', 'sign in', 'access denied']):
                                            logger.debug("Login required")
                                            is_html = True
                                            break
                                        logger.debug("Received HTML instead of PDF")
                                        is_html = True
                                        break

                            f.write(chunk)
                            total_size += len(chunk)

                # Cleanup if HTML received
                if is_html:
                    if temp_path.exists():
                        temp_path.unlink()
                    return False

                if not first_chunk:
                    logger.debug("Empty response")
                    if temp_path.exists():
                        temp_path.unlink()
                    continue

                # Validate file size
                if total_size < MIN_PDF_SIZE:
                    logger.debug(f"File too small: {total_size} bytes")
                    temp_path.unlink()
                    return False

                # Validate PDF header
                with open(temp_path, 'rb') as f:
                    if f.read(4) != b'%PDF':
                        logger.debug("Invalid PDF header")
                        temp_path.unlink()
                        return False

                # Atomic rename
                temp_path.replace(save_path)
                return True

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                if temp_path.exists():
                    temp_path.unlink()
                if attempt < self.max_retries - 1:
                    logger.debug(f"Network error, will retry: {type(e).__name__}")
                    continue
                return False

            except requests.exceptions.HTTPError:
                if temp_path.exists():
                    temp_path.unlink()
                return False

            except Exception as e:
                if temp_path.exists():
                    temp_path.unlink()
                logger.debug(f"Download error: {e}")
                if attempt < self.max_retries - 1:
                    continue
                return False

        return False

    @staticmethod
    def validate_pdf(path: Path) -> bool:
        """
        Validate that a file is a valid PDF

        Args:
            path: Path to the file

        Returns:
            True if valid PDF
        """
        if not path.exists():
            return False

        if path.stat().st_size < MIN_PDF_SIZE:
            return False

        with open(path, 'rb') as f:
            return f.read(4) == b'%PDF'
