"""
Global configuration constants
"""

from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List

# Base data directory (parent of cybersec_papers/ package directory)
# Path: cybersec_papers/src/cybersec_papers/config.py -> parent*4 = CybersecurityPaperCrawling/
DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Conference configurations
@dataclass
class ConferenceConfig:
    name: str           # Display name
    dir_name: str       # Directory name for data storage
    years: List[int]    # Default years to crawl
    free_access: bool   # Whether papers are freely accessible


CONFERENCES: Dict[str, ConferenceConfig] = {
    "usenix": ConferenceConfig(
        name="USENIX Security",
        dir_name="USENIX_Security",
        years=[2024, 2023, 2022, 2021, 2020],
        free_access=True,
    ),
    "ndss": ConferenceConfig(
        name="NDSS",
        dir_name="NDSS",
        years=[2024, 2023, 2022, 2021, 2020],
        free_access=True,
    ),
    "ieee_sp": ConferenceConfig(
        name="IEEE S&P",
        dir_name="IEEE_SP",
        years=[2023, 2022, 2021, 2020],  # 2024 behind paywall
        free_access=True,  # After 1-year embargo
    ),
    "acm_ccs": ConferenceConfig(
        name="ACM CCS",
        dir_name="ACM_CCS",
        years=[2024, 2023, 2022, 2021, 2020],
        free_access=False,  # Requires FlareSolverr
    ),
}

# Default settings
DEFAULT_DELAY = 1.0
DEFAULT_WORKERS = 5
DEFAULT_METADATA_FORMAT = "csv"

# FlareSolverr
FLARESOLVERR_URL = "http://localhost:8191/v1"

# User-Agent
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# PDF validation
MIN_PDF_SIZE = 50000  # 50KB minimum

# Logging
LOGS_DIR = Path(__file__).parent.parent.parent.parent / "logs"
