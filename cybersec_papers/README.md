# Cybersecurity Conference Paper Crawler

Modular crawler and converter for downloading research papers from top cybersecurity conferences.

## Supported Conferences

| Conference | Free Access | Notes |
|------------|-------------|-------|
| **USENIX Security** | ✓ | Fully open access |
| **NDSS** | ✓ | Fully open access |
| **IEEE S&P** | ✓* | Open after 1-year embargo (2023 and earlier) |
| **ACM CCS** | ✓** | Requires FlareSolverr; fully open from Jan 2026 |

## Installation

```bash
cd cybersec_papers

# Initialize environment
uv sync

# Optional: Install MinerU for PDF conversion
uv pip install -U "mineru[core]"

# For GPU-accelerated conversion
uv pip install -U "mineru[core,vllm]"
```

## Usage

### Download Papers

```bash
# Download specific conference and years
uv run python -m cybersec_papers download -c ieee_sp -y 2023 2022

# Download all conferences
uv run python -m cybersec_papers download --all

# With FlareSolverr (for IEEE)
uv run python -m cybersec_papers download -c ieee_sp -y 2023 --flaresolverr
```

### Convert PDFs to Markdown

```bash
# Convert specific conference
uv run python -m cybersec_papers convert -c ieee_sp -y 2023

# Convert all
uv run python -m cybersec_papers convert --all

# Force re-conversion
uv run python -m cybersec_papers convert -c usenix -y 2024 --force
```

### Download and Convert (One Command)

```bash
# Download and convert in one step
uv run python -m cybersec_papers run -c usenix -y 2024

# All conferences
uv run python -m cybersec_papers run --all
```

### Check Status

```bash
uv run python -m cybersec_papers status
```

## CLI Options

### Common Options

| Option | Description |
|--------|-------------|
| `-c, --conference` | Conference key: `usenix`, `ndss`, `ieee_sp`, `acm_ccs` |
| `-y, --years` | Years to process (e.g., `-y 2023 2022`) |
| `--all` | Process all conferences |
| `--workers` | Concurrent downloads/conversions |

### Download Options

| Option | Description |
|--------|-------------|
| `--delay` | Delay between requests (default: 1.0s) |
| `--format` | Metadata format: `csv`, `json`, `txt`, `all` |
| `--flaresolverr` | Use FlareSolverr for IEEE |
| `--cookies` | ACM cookies file path |

### Convert Options

| Option | Description |
|--------|-------------|
| `--backend` | MinerU backend: `auto`, `vlm-transformers`, `vlm-vllm` |
| `--force` | Force re-conversion of existing files |
| `--install-guide` | Show MinerU installation guide |

## Output Structure

```
{CONFERENCE}/
├── {YEAR}/
│   ├── papers/
│   │   ├── paper_title.pdf
│   │   └── ...
│   ├── markdown/
│   │   ├── paper_title/
│   │   │   └── paper_title.md
│   │   └── ...
│   └── metadata.csv
└── ...
```

## FlareSolverr Setup

Required for ACM CCS and optionally for IEEE S&P to bypass anti-bot protection:

```bash
# Start FlareSolverr container
docker run -d -p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest
```

## Architecture

```
src/cybersec_papers/
├── config.py           # Global configuration
├── main.py             # CLI entry point
├── core/               # Core modules
│   ├── base_crawler.py # Abstract base class
│   ├── downloader.py   # PDF downloader with retry
│   ├── metadata.py     # Metadata management
│   ├── session.py      # HTTP session management
│   └── utils.py        # Utility functions
├── crawlers/           # Conference-specific crawlers
│   ├── usenix.py
│   ├── ndss.py
│   ├── ieee_sp.py
│   └── acm_ccs.py
├── services/           # External service integrations
│   ├── flaresolverr.py
│   ├── semantic_scholar.py
│   └── arxiv.py
└── converter/          # PDF to Markdown conversion
    └── mineru.py
```

## License

MIT
