#!/usr/bin/env python3
"""
PDF 转 Markdown 脚本

使用 MinerU 将学术论文PDF转换为Markdown格式，支持GPU加速和并行处理。

用法:
    # 查看转换进度
    uv run python convert_pdf.py --status

    # 运行转换（默认6个并行worker）
    uv run python convert_pdf.py

    # 自定义worker数
    uv run python convert_pdf.py --workers 8

设计原则：
1. 子进程隔离：每个转换在独立subprocess中运行，自动释放内存
2. 批次处理：每批30个文件，批次间检查内存
3. 超时处理：单文件180秒超时，避免僵尸进程
"""

import logging
import time
import sys
import os
import gc
import signal
import subprocess
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from typing import Tuple, List

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.cybersec_papers.config import CONFERENCES, DATA_DIR

# ========== 核心配置 ==========
# 基于实测：6个worker峰值内存~15GB，60GB系统安全运行
MAX_WORKERS = 6
TIMEOUT_PER_FILE = 180  # 3分钟超时（实测单文件最长约80秒）
MEMORY_SAFE_THRESHOLD_GB = 15  # 可用内存低于此值时暂停
BATCH_SIZE = 30  # 每批处理文件数
# ==============================


def setup_logger(log_file: Path) -> logging.Logger:
    """创建logger"""
    logger = logging.getLogger('v6')
    logger.setLevel(logging.INFO)
    logger.handlers = []

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    fh = logging.FileHandler(log_file, mode='a')
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger


def get_memory_available_gb() -> float:
    """获取可用内存(GB)"""
    try:
        import psutil
        return psutil.virtual_memory().available / 1024**3
    except:
        return 30.0  # 默认假设有30GB可用


def get_pending_files(conferences: List[str], years: List[int]) -> List[Tuple[str, str]]:
    """获取待转换的文件列表

    Returns:
        List of (pdf_path, output_dir)
    """
    pending = []
    for conference in conferences:
        conf_config = CONFERENCES.get(conference)
        if not conf_config:
            continue

        for year in years:
            pdf_dir = DATA_DIR / conf_config.dir_name / str(year) / 'papers'
            output_dir = DATA_DIR / conf_config.dir_name / str(year) / 'markdown'

            if not pdf_dir.exists():
                continue

            # 过滤：50KB-50MB，排除完整论文集
            for pdf_path in pdf_dir.glob('*.pdf'):
                size = pdf_path.stat().st_size
                if not (50000 < size < 50 * 1024 * 1024):
                    continue
                if 'Proceedings' in pdf_path.name:
                    continue

                # 检查是否已转换
                md_dir = output_dir / pdf_path.stem
                md_file = md_dir / f"{pdf_path.stem}.md"
                md_file_auto = md_dir / "auto" / f"{pdf_path.stem}.md"

                if not (md_file.exists() or md_file_auto.exists()):
                    pending.append((str(pdf_path), str(md_dir)))

    return pending


def convert_single_pdf(args: Tuple[str, str]) -> Tuple[bool, str, str]:
    """
    在子进程中转换单个PDF

    使用subprocess而非直接调用，确保：
    1. 完全隔离的内存空间
    2. 进程结束后内存自动释放
    3. 超时可以强制终止
    """
    pdf_path, output_dir = args
    pdf_name = Path(pdf_path).name

    try:
        # 创建输出目录
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # 构建mineru CLI命令
        env = os.environ.copy()
        env['HF_ENDPOINT'] = 'https://hf-mirror.com'
        env['PYTHONIOENCODING'] = 'utf-8'

        cli_args = ['-p', pdf_path, '-o', str(Path(output_dir).parent)]
        args_str = ', '.join(f'"{a}"' for a in cli_args)
        mineru_code = f'import sys; sys.argv = ["mineru", {args_str}]; from mineru.cli.client import main; main()'
        cmd = [sys.executable, '-c', mineru_code]

        # 运行转换
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            timeout=TIMEOUT_PER_FILE,
        )

        if result.returncode == 0:
            return (True, pdf_name, "OK")
        else:
            error_msg = result.stderr.decode()[:100] if result.stderr else "Unknown error"
            return (False, pdf_name, error_msg)

    except subprocess.TimeoutExpired:
        return (False, pdf_name, f"Timeout (>{TIMEOUT_PER_FILE}s)")
    except Exception as e:
        return (False, pdf_name, str(e)[:100])


def run_conversion(
    conferences: List[str],
    years: List[int],
    logger: logging.Logger,
    max_workers: int = MAX_WORKERS,
) -> Tuple[int, int]:
    """
    运行转换任务

    Args:
        conferences: 会议列表
        years: 年份列表
        logger: 日志记录器
        max_workers: 并行worker数

    Returns:
        (success_count, failed_count)
    """
    # 获取待处理文件
    all_tasks = get_pending_files(conferences, years)

    if not all_tasks:
        logger.info("所有文件已转换完成 ✅")
        return 0, 0

    total = len(all_tasks)
    logger.info(f"待转换: {total} 个文件")
    logger.info(f"配置: {max_workers} workers, {TIMEOUT_PER_FILE}s超时, 每批{BATCH_SIZE}个")

    # 检查初始内存
    mem_available = get_memory_available_gb()
    logger.info(f"可用内存: {mem_available:.1f}GB")

    if mem_available < MEMORY_SAFE_THRESHOLD_GB:
        logger.warning(f"内存不足 ({mem_available:.1f}GB < {MEMORY_SAFE_THRESHOLD_GB}GB)，等待释放...")
        time.sleep(30)
        gc.collect()

    success_count = 0
    failed_count = 0
    start_time = time.time()

    # 分批处理
    for batch_start in range(0, total, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total)
        batch_tasks = all_tasks[batch_start:batch_end]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

        logger.info(f"\n=== 批次 {batch_num}/{total_batches} ({len(batch_tasks)}个文件) ===")

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {
                executor.submit(convert_single_pdf, task): task
                for task in batch_tasks
            }

            for future in as_completed(future_to_task):
                task = future_to_task[future]
                current = success_count + failed_count + 1

                try:
                    success, name, msg = future.result(timeout=TIMEOUT_PER_FILE + 30)

                    if success:
                        success_count += 1
                        if current % 5 == 0 or current == total:
                            elapsed = time.time() - start_time
                            rate = current / elapsed * 60  # 文件/分钟
                            eta = (total - current) / rate if rate > 0 else 0
                            mem = get_memory_available_gb()
                            logger.info(
                                f"[{current}/{total}] ✓ {current*100//total}% "
                                f"| {rate:.1f}文件/分 | ETA:{eta:.0f}分 "
                                f"| 内存:{mem:.0f}GB | {name[:35]}"
                            )
                    else:
                        failed_count += 1
                        logger.warning(f"[{current}/{total}] ✗ {name[:40]}: {msg[:50]}")

                except FuturesTimeoutError:
                    failed_count += 1
                    logger.warning(f"[{current}/{total}] ✗ {Path(task[0]).name[:40]}: Future超时")
                except Exception as e:
                    failed_count += 1
                    logger.warning(f"[{current}/{total}] ✗ {Path(task[0]).name[:40]}: {str(e)[:50]}")

        # 批次结束后检查内存
        gc.collect()
        mem = get_memory_available_gb()

        if mem < MEMORY_SAFE_THRESHOLD_GB:
            logger.warning(f"内存不足 ({mem:.1f}GB)，暂停60秒...")
            time.sleep(60)
            gc.collect()

    # 最终统计
    elapsed = time.time() - start_time
    logger.info(f"\n=== 完成 ===")
    logger.info(f"成功: {success_count}/{total}")
    logger.info(f"失败: {failed_count}/{total}")
    logger.info(f"耗时: {elapsed/60:.1f}分钟")
    logger.info(f"速度: {total/elapsed*60:.1f}文件/分钟")

    return success_count, failed_count


def get_status() -> dict:
    """获取转换进度"""
    from src.cybersec_papers.converter.mineru import MineruConverter
    converter = MineruConverter(force=False)
    return converter.get_status()


def print_status():
    """打印转换状态"""
    status = get_status()
    print("\n=== PDF 转 Markdown 进度 ===\n")

    total_pdf = 0
    total_md = 0

    for conf_key, conf_status in status.items():
        conf_pdf = sum(y['pdf_count'] for y in conf_status['years'].values())
        conf_md = sum(y['markdown_count'] for y in conf_status['years'].values())
        remaining = conf_pdf - conf_md
        pct = conf_md * 100 // conf_pdf if conf_pdf > 0 else 0
        print(f"{conf_status['name']}: {conf_md}/{conf_pdf} ({pct}%) - 剩余 {remaining}")
        total_pdf += conf_pdf
        total_md += conf_md

    pct = total_md * 100 // total_pdf if total_pdf > 0 else 0
    print(f"\n总计: {total_md}/{total_pdf} ({pct}%)")
    print(f"剩余: {total_pdf - total_md} 篇")
    print(f"\n系统内存: {get_memory_available_gb():.1f}GB 可用\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='PDF转Markdown V6 (稳定高效版)')
    parser.add_argument('--status', action='store_true', help='显示状态')
    parser.add_argument('--workers', type=int, default=MAX_WORKERS, help=f'并行worker数 (默认{MAX_WORKERS})')
    parser.add_argument('--conferences', nargs='+', default=['ieee_sp', 'acm_ccs', 'usenix', 'ndss'],
                        help='要处理的会议')
    parser.add_argument('--years', nargs='+', type=int, default=[2024, 2023, 2022, 2021, 2020],
                        help='要处理的年份')
    args = parser.parse_args()

    if args.status:
        print_status()
        return

    # 设置日志
    log_dir = Path(__file__).parent.parent / 'logs'
    log_dir.mkdir(exist_ok=True)
    logger = setup_logger(log_dir / 'convert_pdf.log')

    logger.info("=" * 50)
    logger.info("PDF转Markdown 启动")
    logger.info(f"会议: {args.conferences}")
    logger.info(f"年份: {args.years}")
    logger.info("=" * 50)

    try:
        run_conversion(
            conferences=args.conferences,
            years=args.years,
            logger=logger,
            max_workers=args.workers,
        )
    except KeyboardInterrupt:
        logger.info("\n用户中断")
    except Exception as e:
        logger.error(f"异常: {e}")
        raise


if __name__ == '__main__':
    main()
