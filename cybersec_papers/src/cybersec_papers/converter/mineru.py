"""
MinerU PDF to Markdown converter wrapper

Supports both CLI-based (subprocess) and Python API-based conversion.
Uses ProcessPoolExecutor for true parallelism on CPU/GPU intensive tasks.

Key optimizations:
1. ProcessPoolExecutor instead of ThreadPoolExecutor for true parallelism
2. Python API when available (avoids subprocess overhead)
3. Auto-detection of optimal worker count based on GPU/CPU
4. Progress tracking with rich output
"""

import logging
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
from pathlib import Path
from typing import List, Optional, Tuple

from ..config import DATA_DIR, CONFERENCES

logger = logging.getLogger(__name__)


def _convert_single_pdf_worker(args: Tuple[str, str, str, bool]) -> Tuple[bool, str, str]:
    """
    Worker function for ProcessPoolExecutor (must be at module level for pickling)

    Args:
        args: (pdf_path_str, output_dir_str, backend, force)

    Returns:
        (success, pdf_name, message)
    """
    pdf_path_str, output_dir_str, backend, force = args
    pdf_path = Path(pdf_path_str)
    output_dir = Path(output_dir_str)

    # Check if already converted
    md_file = output_dir / f"{pdf_path.stem}.md"
    if md_file.exists() and not force:
        return (True, pdf_path.name, "Already converted, skipped")

    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Try Python API first (more efficient, no subprocess overhead)
        success, msg = _convert_with_python_api(pdf_path, output_dir, backend)
        if success:
            return (True, pdf_path.name, msg)

        # Fallback to CLI
        success, msg = _convert_with_cli(pdf_path, output_dir, backend)
        return (success, pdf_path.name, msg)

    except Exception as e:
        return (False, pdf_path.name, f"Error: {str(e)[:200]}")


def _convert_with_python_api(pdf_path: Path, output_dir: Path, backend: str) -> Tuple[bool, str]:
    """
    Convert using MinerU Python API (faster, no subprocess overhead)

    This directly uses MinerU's internal pipeline for maximum efficiency.
    """
    try:
        from magic_pdf.data.data_reader_writer import FileBasedDataReader, FileBasedDataWriter
        from magic_pdf.pipe.UNIPipe import UNIPipe

        # Read PDF bytes
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()

        # Determine output paths
        images_dir = output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        # Create writer
        writer = FileBasedDataWriter(str(output_dir))

        # Use UNIPipe for automatic mode detection
        pipe = UNIPipe(pdf_bytes, {"_pdf_type": ""}, writer)

        # Run pipeline stages
        pipe.pipe_classify()
        pipe.pipe_analyze()
        pipe.pipe_parse()

        # Generate markdown
        md_content = pipe.pipe_mk_markdown(str(images_dir), drop_mode="none")

        # Write output
        md_file = output_dir / f"{pdf_path.stem}.md"
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(md_content)

        return (True, "Converted via Python API")

    except ImportError:
        return (False, "MinerU Python API not available")
    except Exception as e:
        return (False, f"Python API error: {str(e)[:150]}")


def _convert_with_cli(pdf_path: Path, output_dir: Path, backend: str) -> Tuple[bool, str]:
    """
    Convert using MinerU CLI (subprocess fallback)
    """
    try:
        # Set up environment
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        if 'HF_ENDPOINT' not in env:
            env['HF_ENDPOINT'] = 'https://hf-mirror.com'

        # Build mineru CLI arguments
        args = ['-p', str(pdf_path), '-o', str(output_dir.parent)]
        if backend and backend not in ('auto', 'pipeline'):
            args.extend(['-b', backend])

        # Use python -c to call mineru.cli.client.main() (works in any venv)
        args_str = ', '.join(f'"{a}"' for a in args)
        mineru_code = f'import sys; sys.argv = ["mineru", {args_str}]; from mineru.cli.client import main; main()'
        cmd = [sys.executable, '-c', mineru_code]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min timeout
            env=env
        )

        if result.returncode == 0:
            return (True, "Converted via mineru CLI")

        return (False, f"CLI error: {result.stderr[:200] if result.stderr else 'mineru failed'}")

    except subprocess.TimeoutExpired:
        return (False, "Conversion timeout (>10 min)")
    except FileNotFoundError:
        return (False, "mineru/magic-pdf CLI not found")
    except Exception as e:
        return (False, f"CLI error: {str(e)[:150]}")


class MineruConverter:
    """
    MinerU PDF to Markdown converter wrapper

    Features:
    - Uses ProcessPoolExecutor for true parallelism (bypasses Python GIL)
    - Auto-detects optimal worker count based on GPU/CPU availability
    - Supports both Python API and CLI-based conversion
    - Progress tracking and resumable conversion
    """

    def __init__(
        self,
        base_dir: Path = None,
        max_workers: int = None,
        backend: str = 'auto',
        force: bool = False,
    ):
        """
        Initialize converter

        Args:
            base_dir: Base directory for data
            max_workers: Maximum concurrent conversions
                        None = auto-detect (GPU count or CPU count / 2)
            backend: MinerU backend ('auto', 'vlm-transformers', 'vlm-vllm')
            force: Force re-conversion of existing files
        """
        self.base_dir = Path(base_dir) if base_dir else DATA_DIR
        self.backend = backend
        self.force = force

        # Auto-detect optimal worker count
        if max_workers is None:
            self.max_workers = self._detect_optimal_workers()
        else:
            self.max_workers = max_workers

        self._mineru_available = None

    def _detect_optimal_workers(self) -> int:
        """
        Detect optimal number of workers based on available resources

        Returns:
            Recommended worker count
        """
        try:
            import torch
            if torch.cuda.is_available():
                gpu_count = torch.cuda.device_count()
                # For GPU: use GPU count (each worker can use one GPU)
                # MinerU is GPU-memory intensive, so 1 worker per GPU is optimal
                logger.info(f"Detected {gpu_count} GPU(s), using {gpu_count} workers")
                return max(1, gpu_count)
        except ImportError:
            pass

        # For CPU: use half of cores (PDF conversion is memory intensive)
        cpu_workers = max(1, cpu_count() // 2)
        logger.info(f"No GPU detected, using {cpu_workers} CPU workers")
        return cpu_workers

    def check_mineru_available(self) -> bool:
        """
        Check if MinerU is available

        Returns:
            True if MinerU is installed
        """
        if self._mineru_available is not None:
            return self._mineru_available

        try:
            result = subprocess.run(
                [sys.executable, '-c', 'import magic_pdf'],
                capture_output=True,
                timeout=10
            )
            self._mineru_available = result.returncode == 0
        except Exception:
            self._mineru_available = False

        return self._mineru_available

    def check_gpu_available(self) -> bool:
        """Check if GPU is available for acceleration"""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def get_install_guide(self) -> str:
        """
        Get MinerU installation guide

        Returns:
            Installation instructions
        """
        return """
MinerU Installation Guide
=========================

1. Basic Installation:
   pip install -U "mineru[core]"
   # or with uv:
   uv pip install -U "mineru[core]"

2. VLM Accelerated Version (higher quality, requires GPU):
   pip install -U "mineru[core,vllm]"

3. CUDA Requirements:
   - CUDA 11.8 / 12.4 / 12.6 / 12.8 (optional, for GPU acceleration)
   - Check GPU compatibility: nvidia-smi

4. Download Models (required after installation):
   mineru-models download

5. Optimal Performance:
   - GPU: 1 worker per GPU (auto-detected)
   - CPU: Half of CPU cores (auto-detected)
   - Use --workers N to override

For more details: https://github.com/opendatalab/MinerU
"""

    def convert_pdf(self, pdf_path: Path, output_dir: Path = None) -> bool:
        """
        Convert a single PDF to Markdown

        Args:
            pdf_path: Path to PDF file
            output_dir: Output directory (default: alongside PDF)

        Returns:
            True if conversion successful
        """
        if not self.check_mineru_available():
            logger.error("MinerU is not installed")
            return False

        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            logger.error(f"PDF file not found: {pdf_path}")
            return False

        # Determine output directory
        if output_dir is None:
            output_dir = pdf_path.parent.parent / 'markdown' / pdf_path.stem
        output_dir = Path(output_dir)

        # Use the worker function directly
        success, name, msg = _convert_single_pdf_worker(
            (str(pdf_path), str(output_dir), self.backend, self.force)
        )

        if success:
            logger.info(f"Converted: {name} - {msg}")
        else:
            logger.error(f"Failed: {name} - {msg}")

        return success

    def convert_directory(self, pdf_dir: Path, output_dir: Path = None) -> tuple:
        """
        Convert all PDFs in a directory using parallel processing

        Args:
            pdf_dir: Directory containing PDFs
            output_dir: Output directory

        Returns:
            Tuple of (success_count, total_count)
        """
        pdf_dir = Path(pdf_dir)
        if not pdf_dir.exists():
            logger.error(f"Directory not found: {pdf_dir}")
            return 0, 0

        # Get all PDF files (filter small/invalid ones)
        pdf_files = [f for f in pdf_dir.glob('*.pdf') if f.stat().st_size > 50000]
        if not pdf_files:
            logger.warning(f"No valid PDF files found in {pdf_dir}")
            return 0, 0

        total_count = len(pdf_files)
        logger.info(f"Found {total_count} PDF files to convert")

        # Default output directory
        if output_dir is None:
            output_dir = pdf_dir.parent / 'markdown'
        output_dir = Path(output_dir)

        # Filter out already converted files
        # MinerU outputs to: {output_dir}/{pdf_stem}/auto/{pdf_stem}.md
        skipped_count = 0
        if not self.force:
            remaining_files = []
            for pdf_path in pdf_files:
                md_dir = output_dir / pdf_path.stem
                # Check both possible locations (with and without 'auto' subdir)
                md_file = md_dir / f"{pdf_path.stem}.md"
                md_file_auto = md_dir / "auto" / f"{pdf_path.stem}.md"
                if md_file.exists() or md_file_auto.exists():
                    skipped_count += 1
                else:
                    remaining_files.append(pdf_path)
            pdf_files = remaining_files

            if skipped_count > 0:
                logger.info(f"Skipping {skipped_count} already converted files")

        if not pdf_files:
            logger.info("All files already converted")
            return skipped_count, total_count

        # Prepare tasks for parallel execution
        tasks = [
            (str(pdf_path), str(output_dir / pdf_path.stem), self.backend, self.force)
            for pdf_path in pdf_files
        ]

        success_count = skipped_count
        failed_count = 0

        # Use ProcessPoolExecutor for true parallelism
        logger.info(f"Starting conversion with {self.max_workers} parallel workers...")

        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(_convert_single_pdf_worker, task): task[0]
                for task in tasks
            }

            for i, future in enumerate(as_completed(futures), 1):
                pdf_path = futures[future]
                try:
                    success, name, msg = future.result()
                    if success:
                        if "skipped" not in msg.lower():
                            success_count += 1
                        logger.info(f"[{i}/{len(tasks)}] ✓ {name[:50]}: {msg}")
                    else:
                        failed_count += 1
                        logger.error(f"[{i}/{len(tasks)}] ✗ {name[:50]}: {msg}")
                except Exception as e:
                    failed_count += 1
                    logger.error(f"[{i}/{len(tasks)}] ✗ {Path(pdf_path).name}: {str(e)[:100]}")

        logger.info(f"Conversion complete: {success_count}/{total_count} succeeded, {failed_count} failed")
        return success_count, total_count

    def convert_conference(
        self,
        conference: str,
        years: Optional[List[int]] = None,
    ) -> tuple:
        """
        Convert all papers for a conference

        Args:
            conference: Conference key (e.g., 'ieee_sp')
            years: List of years to convert

        Returns:
            Tuple of (success_count, total_count)
        """
        conf_config = CONFERENCES.get(conference)
        if not conf_config:
            logger.error(f"Unknown conference: {conference}")
            return 0, 0

        if years is None:
            years = conf_config.years

        total_success = 0
        total_count = 0

        for year in years:
            pdf_dir = self.base_dir / conf_config.dir_name / str(year) / 'papers'
            output_dir = self.base_dir / conf_config.dir_name / str(year) / 'markdown'

            if not pdf_dir.exists():
                logger.warning(f"No papers directory for {conf_config.name} {year}")
                continue

            logger.info(f"Converting {conf_config.name} {year}...")
            success, total = self.convert_directory(pdf_dir, output_dir)
            total_success += success
            total_count += total

        return total_success, total_count

    def convert_all(self) -> tuple:
        """
        Convert all papers for all conferences

        Returns:
            Tuple of (success_count, total_count)
        """
        total_success = 0
        total_count = 0

        for conf_key in CONFERENCES:
            success, total = self.convert_conference(conf_key)
            total_success += success
            total_count += total

        return total_success, total_count

    def get_status(self) -> dict:
        """
        Get conversion status for all conferences

        Returns:
            Dictionary with status information
        """
        status = {}

        for conf_key, conf_config in CONFERENCES.items():
            conf_status = {
                'name': conf_config.name,
                'years': {},
            }

            for year in conf_config.years:
                pdf_dir = self.base_dir / conf_config.dir_name / str(year) / 'papers'
                md_dir = self.base_dir / conf_config.dir_name / str(year) / 'markdown'

                # Filter: 50KB-35MB, exclude Proceedings (35MB limit due to pypdf decompression limits)
                pdf_count = len([
                    f for f in pdf_dir.glob('*.pdf')
                    if 50000 < f.stat().st_size < 35 * 1024 * 1024
                    and 'Proceedings' not in f.name
                ]) if pdf_dir.exists() else 0
                md_count = 0

                if md_dir.exists():
                    for item in md_dir.iterdir():
                        if item.is_dir():
                            # Check both locations (with and without 'auto' subdir)
                            md_file = item / f"{item.name}.md"
                            md_file_auto = item / "auto" / f"{item.name}.md"
                            if md_file.exists() or md_file_auto.exists():
                                md_count += 1

                conf_status['years'][year] = {
                    'pdf_count': pdf_count,
                    'markdown_count': md_count,
                    'remaining': pdf_count - md_count,
                }

            status[conf_key] = conf_status

        return status
