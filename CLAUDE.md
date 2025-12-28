# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated crawler suite for downloading research papers from top cybersecurity conferences:
- **USENIX Security** - Free downloads
- **NDSS** - Free downloads
- **IEEE S&P** - Open access after 1-year embargo (2023 and earlier should be free)
- **ACM CCS** - Not yet implemented (will be fully open access from January 2026)

## Open Access Policy Notes

### IEEE S&P
According to [IEEE S&P CFP](https://sp2025.ieee-security.org/cfpapers.html):
- Papers are published open access immediately upon acceptance
- After the symposium, papers go behind a paywall for **1 year**
- After 1 year, papers become open access again

**Current status** (as of late 2024):
- 2023 and earlier: Should be freely accessible
- 2024: Behind paywall until ~May 2025

### ACM CCS
- ACM Digital Library will become fully open access from **January 2026**
- Currently, some papers available via OpenTOC

## Commands

### Running Crawlers

```bash
# USENIX Security
uv run python crawler_usenix_security.py -y 2023 2024

# NDSS
uv run python crawler_ndss.py -y 2023 2024

# IEEE S&P (no auth needed for open access papers)
uv run python crawler_ieee_sp.py -y 2023 2022 2021
```

### Common Options (all crawlers)

- `-y, --years`: Years to download (e.g., `-y 2021 2022 2023`)
- `-d, --dir`: Custom save directory
- `--delay`: Delay between requests in seconds (default: 1.0)
- `--workers`: Concurrent download threads (default: 5)
- `--format`: Metadata format - `csv`, `txt`, `json`, or `all` (default: `csv`)

### Monitoring

```bash
./check_status.sh              # Check progress and statistics
tail -f logs/ndss_download.log # Real-time log monitoring
```

### Background Execution

```bash
nohup uv run python crawler_ndss.py -y 2023 2024 --format csv --workers 10 > logs/ndss_download.log 2>&1 &
```

## Architecture

### Processing Pipeline

```
URL Discovery → HTML Parsing → PDF Link Extraction → Concurrent Download → Metadata Saving
```

### Key Design Patterns

- **Class-Based Scrapers**: `USENIXSecurityCrawler`, `NDSSCrawler`, `IEEESPCrawler`
- **Thread-Safe Concurrency**: ThreadPoolExecutor with lock-based counter synchronization
- **Retry with Exponential Backoff**: Up to 5 retries with delays (1s, 2s, up to 5s max)
- **Content Validation**: PDF magic bytes, Content-Type headers, minimum file size checks (50KB+)
- **Atomic File Operations**: Temp files with atomic rename to prevent partial downloads

### URL Discovery Strategies

Each conference has different page structures requiring custom extraction logic:
- **NDSS**: Tries multiple URL patterns (`/ndss{year}/accepted-papers/`, `/program/`), then visits individual paper detail pages
- **USENIX**: Multiple fallback URL patterns with both direct PDF links and presentation page inference
- **IEEE S&P**: Uses IEEE Xplore REST API to get paper list, downloads via stamp.jsp

### Output Structure

```
{CONFERENCE}/YYYY/papers/*.pdf
{CONFERENCE}/YYYY/metadata.csv
```

## Dependencies

- `requests` - HTTP client
- `beautifulsoup4` + `lxml` - HTML parsing
- Python >= 3.8
- `uv` package manager
