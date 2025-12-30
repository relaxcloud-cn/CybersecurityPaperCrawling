"""
Unified CLI entry point for cybersec-papers

Usage:
    # Download papers
    uv run python -m cybersec_papers download -c ieee_sp -y 2023 2022
    uv run python -m cybersec_papers download --all

    # Convert to Markdown
    uv run python -m cybersec_papers convert -c ieee_sp -y 2023
    uv run python -m cybersec_papers convert --all

    # Download and convert
    uv run python -m cybersec_papers run -c ieee_sp -y 2023
    uv run python -m cybersec_papers run --all

    # Check status
    uv run python -m cybersec_papers status
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

from .config import CONFERENCES, DATA_DIR
from .crawlers import USENIXSecurityCrawler, NDSSCrawler, IEEESPCrawler, ACMCCSCrawler
from .converter import MineruConverter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def get_crawler(conference: str, **kwargs):
    """
    Get crawler instance for a conference

    Args:
        conference: Conference key
        **kwargs: Additional arguments for crawler

    Returns:
        Crawler instance
    """
    crawlers = {
        'usenix': USENIXSecurityCrawler,
        'ndss': NDSSCrawler,
        'ieee_sp': IEEESPCrawler,
        'acm_ccs': ACMCCSCrawler,
    }

    crawler_class = crawlers.get(conference)
    if not crawler_class:
        raise ValueError(f"Unknown conference: {conference}")

    return crawler_class(**kwargs)


def cmd_download(args):
    """Download papers command"""
    conferences = []
    if args.all:
        conferences = list(CONFERENCES.keys())
    elif args.conference:
        conferences = [args.conference]
    else:
        logger.error("Specify --conference or --all")
        return 1

    for conf_key in conferences:
        conf_config = CONFERENCES.get(conf_key)
        if not conf_config:
            logger.error(f"Unknown conference: {conf_key}")
            continue

        years = args.years if args.years else conf_config.years

        logger.info(f"{'='*60}")
        logger.info(f"Downloading {conf_config.name} papers for years: {years}")
        logger.info(f"{'='*60}")

        kwargs = {
            'delay': args.delay,
            'max_workers': args.workers,
            'metadata_format': args.format,
        }

        # Add FlareSolverr option for IEEE and ACM
        if conf_key in ['ieee_sp'] and args.flaresolverr:
            kwargs['use_flaresolverr'] = True

        if conf_key == 'acm_ccs' and args.cookies:
            kwargs['cookies_file'] = args.cookies

        try:
            crawler = get_crawler(conf_key, **kwargs)
            crawler.crawl(years=years)
        except Exception as e:
            logger.error(f"Failed to crawl {conf_config.name}: {e}")
            if args.debug:
                import traceback
                traceback.print_exc()

    return 0


def cmd_convert(args):
    """Convert papers to Markdown command"""
    if not args.all and not args.conference:
        logger.error("Specify --conference or --all")
        return 1

    converter = MineruConverter(
        max_workers=args.workers,
        backend=args.backend,
        force=args.force,
    )

    if not converter.check_mineru_available():
        logger.error("MinerU is not installed")
        print(converter.get_install_guide())
        return 1

    if args.all:
        success, total = converter.convert_all()
    else:
        years = args.years if args.years else None
        success, total = converter.convert_conference(args.conference, years)

    logger.info(f"Conversion complete: {success}/{total} files")
    return 0


def cmd_run(args):
    """Download and convert command"""
    # First download
    result = cmd_download(args)
    if result != 0:
        return result

    # Then convert
    return cmd_convert(args)


def cmd_status(args):
    """Show status command"""
    print("\n" + "=" * 70)
    print("Cybersecurity Papers Status")
    print("=" * 70)

    # Download status
    print("\n📥 Download Status:")
    print("-" * 50)

    for conf_key, conf_config in CONFERENCES.items():
        print(f"\n{conf_config.name}:")
        for year in conf_config.years:
            pdf_dir = DATA_DIR / conf_config.dir_name / str(year) / 'papers'
            if pdf_dir.exists():
                pdf_count = len(list(pdf_dir.glob('*.pdf')))
                print(f"  {year}: {pdf_count} papers")
            else:
                print(f"  {year}: (not downloaded)")

    # Conversion status
    print("\n\n📄 Conversion Status:")
    print("-" * 50)

    converter = MineruConverter()
    status = converter.get_status()

    for conf_key, conf_status in status.items():
        print(f"\n{conf_status['name']}:")
        for year, year_status in conf_status['years'].items():
            pdf_count = year_status['pdf_count']
            md_count = year_status['markdown_count']
            remaining = year_status['remaining']

            if pdf_count > 0:
                if remaining == 0:
                    print(f"  {year}: {md_count}/{pdf_count} converted ✓")
                else:
                    print(f"  {year}: {md_count}/{pdf_count} converted ({remaining} remaining)")
            else:
                print(f"  {year}: (no PDFs)")

    # MinerU status
    print("\n\n🔧 MinerU Status:")
    print("-" * 50)
    if converter.check_mineru_available():
        print("  ✓ MinerU is installed")
    else:
        print("  ✗ MinerU is not installed")
        print("  Run 'cybersec-papers convert --install-guide' for installation instructions")

    print()
    return 0


def cli():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Cybersecurity Conference Paper Crawler and Converter',
        epilog='''
Examples:
  # Download IEEE S&P papers for 2023 and 2022
  %(prog)s download -c ieee_sp -y 2023 2022

  # Download all conferences
  %(prog)s download --all

  # Convert papers to Markdown
  %(prog)s convert -c ieee_sp -y 2023

  # Download and convert in one command
  %(prog)s run -c usenix -y 2024

  # Check status
  %(prog)s status
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Download command
    download_parser = subparsers.add_parser('download', help='Download papers')
    download_parser.add_argument('-c', '--conference', choices=list(CONFERENCES.keys()),
                                  help='Conference to download')
    download_parser.add_argument('-y', '--years', nargs='+', type=int,
                                  help='Years to download')
    download_parser.add_argument('--all', action='store_true',
                                  help='Download all conferences')
    download_parser.add_argument('--delay', type=float, default=1.0,
                                  help='Delay between requests (seconds)')
    download_parser.add_argument('--workers', type=int, default=5,
                                  help='Max concurrent downloads')
    download_parser.add_argument('--format', choices=['txt', 'csv', 'json', 'all'],
                                  default='csv', help='Metadata format')
    download_parser.add_argument('--flaresolverr', action='store_true',
                                  help='Use FlareSolverr for IEEE')
    download_parser.add_argument('--cookies', type=str,
                                  help='ACM cookies file path')
    download_parser.add_argument('--debug', action='store_true',
                                  help='Enable debug output')

    # Convert command
    convert_parser = subparsers.add_parser('convert', help='Convert PDFs to Markdown')
    convert_parser.add_argument('-c', '--conference', choices=list(CONFERENCES.keys()),
                                 help='Conference to convert')
    convert_parser.add_argument('-y', '--years', nargs='+', type=int,
                                 help='Years to convert')
    convert_parser.add_argument('--all', action='store_true',
                                 help='Convert all conferences')
    convert_parser.add_argument('--workers', type=int, default=2,
                                 help='Max concurrent conversions')
    convert_parser.add_argument('--backend', choices=['auto', 'vlm-transformers', 'vlm-vllm'],
                                 default='auto', help='MinerU backend')
    convert_parser.add_argument('--force', action='store_true',
                                 help='Force re-conversion')
    convert_parser.add_argument('--install-guide', action='store_true',
                                 help='Show MinerU installation guide')

    # Run command (download + convert)
    run_parser = subparsers.add_parser('run', help='Download and convert')
    run_parser.add_argument('-c', '--conference', choices=list(CONFERENCES.keys()),
                             help='Conference to process')
    run_parser.add_argument('-y', '--years', nargs='+', type=int,
                             help='Years to process')
    run_parser.add_argument('--all', action='store_true',
                             help='Process all conferences')
    run_parser.add_argument('--delay', type=float, default=1.0,
                             help='Delay between requests')
    run_parser.add_argument('--workers', type=int, default=5,
                             help='Max concurrent downloads')
    run_parser.add_argument('--format', choices=['txt', 'csv', 'json', 'all'],
                             default='csv', help='Metadata format')
    run_parser.add_argument('--backend', choices=['auto', 'vlm-transformers', 'vlm-vllm'],
                             default='auto', help='MinerU backend')
    run_parser.add_argument('--force', action='store_true',
                             help='Force re-conversion')
    run_parser.add_argument('--flaresolverr', action='store_true',
                             help='Use FlareSolverr')
    run_parser.add_argument('--cookies', type=str,
                             help='ACM cookies file')
    run_parser.add_argument('--debug', action='store_true',
                             help='Debug output')

    # Status command
    status_parser = subparsers.add_parser('status', help='Show download/conversion status')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Handle install-guide flag
    if args.command == 'convert' and getattr(args, 'install_guide', False):
        converter = MineruConverter()
        print(converter.get_install_guide())
        return 0

    # Execute command
    commands = {
        'download': cmd_download,
        'convert': cmd_convert,
        'run': cmd_run,
        'status': cmd_status,
    }

    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(cli())
