# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated crawler suite for downloading research papers from top cybersecurity conferences:
- **USENIX Security** - Free downloads
- **NDSS** - Free downloads
- **IEEE S&P** - Open access after 1-year embargo (2023 and earlier should be free)
- **ACM CCS** - Uses FlareSolverr to bypass Cloudflare protection (will be fully open access from January 2026)

## Project Structure

```
CybersecurityPaperCrawling/
├── cybersec_papers/           # Main package
│   ├── src/cybersec_papers/   # Source code
│   │   ├── crawlers/          # Conference-specific crawlers
│   │   ├── converter/         # PDF to Markdown conversion
│   │   ├── services/          # External services (FlareSolverr, etc.)
│   │   └── core/              # Base classes and utilities
│   ├── convert_pdf.py         # PDF to Markdown script
│   └── pyproject.toml
├── {CONFERENCE}/YYYY/         # Downloaded papers (not in git)
│   ├── papers/*.pdf
│   ├── markdown/*/            # Converted markdown files
│   └── metadata.csv
└── logs/                      # Log files (not in git)
```

## Commands

### Running Crawlers

```bash
cd cybersec_papers

# USENIX Security
uv run python -m cybersec_papers crawl usenix -y 2023 2024

# NDSS
uv run python -m cybersec_papers crawl ndss -y 2023 2024

# IEEE S&P
uv run python -m cybersec_papers crawl ieee_sp -y 2023 2022 2021

# ACM CCS (requires FlareSolverr)
# First start FlareSolverr: docker run -d -p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest
uv run python -m cybersec_papers crawl acm_ccs -y 2023 2022 2021
```

### PDF to Markdown Conversion

```bash
cd cybersec_papers

# Check conversion status
uv run python convert_pdf.py --status

# Run conversion (default 6 parallel workers)
uv run python convert_pdf.py

# Custom worker count
uv run python convert_pdf.py --workers 8

# Specific conferences/years
uv run python convert_pdf.py --conferences usenix ndss --years 2023 2024
```

### Common Options

- `-y, --years`: Years to download (e.g., `-y 2021 2022 2023`)
- `--workers`: Concurrent workers (default: 5 for crawlers, 6 for conversion)
- `--delay`: Delay between requests in seconds (default: 1.0)

## Architecture

### Key Design Patterns

- **Class-Based Scrapers**: `USENIXSecurityCrawler`, `NDSSCrawler`, `IEEESPCrawler`, `ACMCCSCrawler`
- **Subprocess Isolation**: PDF conversion runs in isolated subprocesses for memory safety
- **Retry with Exponential Backoff**: Up to 5 retries with delays
- **Content Validation**: PDF magic bytes, Content-Type headers, file size checks (50KB-35MB)

### Output Structure

```
{CONFERENCE}/YYYY/papers/*.pdf
{CONFERENCE}/YYYY/metadata.csv
{CONFERENCE}/YYYY/markdown/{paper_name}/auto/{paper_name}.md
```

## Dependencies

Main dependencies (see `cybersec_papers/pyproject.toml`):
- `requests`, `beautifulsoup4`, `lxml` - Web scraping
- `mineru` - PDF to Markdown conversion (with GPU support)
- Python >= 3.10
- `uv` package manager

## Open Access Policy Notes

### IEEE S&P
- Papers go behind paywall for 1 year after symposium
- After 1 year, papers become open access again

### ACM CCS
- ACM Digital Library will become fully open access from January 2026
- Currently requires FlareSolverr to bypass Cloudflare protection
