"""
Conference paper crawlers
"""

from .usenix import USENIXSecurityCrawler
from .ndss import NDSSCrawler
from .ieee_sp import IEEESPCrawler
from .acm_ccs import ACMCCSCrawler

__all__ = [
    'USENIXSecurityCrawler',
    'NDSSCrawler',
    'IEEESPCrawler',
    'ACMCCSCrawler',
]
