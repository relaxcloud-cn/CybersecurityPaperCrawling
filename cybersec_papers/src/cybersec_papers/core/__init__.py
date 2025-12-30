"""
Core modules for paper crawling
"""

from .utils import sanitize_filename, ensure_dir
from .session import SessionManager
from .downloader import PDFDownloader
from .metadata import MetadataManager
from .base_crawler import BaseCrawler, PaperInfo
