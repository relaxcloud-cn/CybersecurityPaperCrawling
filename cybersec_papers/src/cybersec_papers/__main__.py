"""
Allow running as: python -m cybersec_papers
"""

from .main import cli
import sys

if __name__ == '__main__':
    sys.exit(cli())
