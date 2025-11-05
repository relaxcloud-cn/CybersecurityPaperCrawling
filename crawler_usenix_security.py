#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
USENIX Security Symposium 论文爬虫
下载USENIX Security会议的论文PDF，并按照官方结构组织目录

目录结构：
USENIX_Security/
    └── YYYY/
        └── papers/
            ├── paper_title.pdf
            └── ...
"""

import os
import re
import sys
import time
import requests
from pathlib import Path
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import csv
import json

# 配置日志
# 确保logs目录存在
logs_dir = Path('logs')
logs_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(logs_dir / 'usenix_download.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class USENIXSecurityCrawler:
    """USENIX Security会议论文爬虫"""
    
    BASE_URL = "https://www.usenix.org"
    CONF_BASE = "https://www.usenix.org/conference/usenixsecurity"
    
    def __init__(self, base_dir="USENIX_Security", delay=1.0, max_workers=5, metadata_format='csv'):
        """
        初始化爬虫
        
        Args:
            base_dir: 保存论文的基础目录
            delay: 请求之间的延迟（秒），避免对服务器造成压力
            max_workers: 并发下载的最大线程数
            metadata_format: 元数据保存格式，可选: 'txt', 'csv', 'json', 'all'
        """
        self.base_dir = Path(base_dir)
        self.delay = delay
        self.max_workers = max_workers
        self.metadata_format = metadata_format
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.download_lock = Lock()  # 用于线程安全的计数器
        self.downloaded_count = 0
        self.failed_count = 0
        
    def sanitize_filename(self, filename):
        """
        清理文件名，移除非法字符
        
        Args:
            filename: 原始文件名
            
        Returns:
            清理后的文件名
        """
        # 移除非法字符
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # 移除多余空格
        filename = re.sub(r'\s+', ' ', filename).strip()
        # 限制长度
        if len(filename) > 200:
            filename = filename[:200]
        return filename
    
    def get_conference_years(self):
        """
        获取可用的会议年份列表
        
        Returns:
            年份列表
        """
        # USENIX Security通常从1990年开始，我们可以尝试获取可用年份
        # 这里提供一个常见年份范围，实际使用时可能需要动态获取
        current_year = 2024
        years = list(range(1990, current_year + 1))
        return years
    
    def get_papers_url(self, year):
        """
        获取指定年份的论文页面URL
        
        Args:
            year: 会议年份
            
        Returns:
            论文页面URL
        """
        # USENIX Security的URL格式通常是：
        # https://www.usenix.org/conference/usenixsecurity{year}/technical-sessions
        # 年份格式可能是2位数（如23, 24）或4位数（如2023, 2024）
        
        year_short = str(year)[-2:]  # 取后两位
        urls_to_try = [
            f"{self.CONF_BASE}{year}/technical-sessions",
            f"{self.CONF_BASE}{year_short}/technical-sessions",
            f"{self.CONF_BASE}{year}/program",
            f"{self.CONF_BASE}{year_short}/program",
            f"{self.CONF_BASE}{year}/papers",
            f"{self.CONF_BASE}{year_short}/papers",
        ]
        
        for url in urls_to_try:
            try:
                response = self.session.get(url, timeout=10)
                if response.status_code == 200:
                    logger.info(f"找到{year}年会议页面: {url}")
                    return url
            except Exception as e:
                logger.debug(f"尝试{url}失败: {e}")
                continue
        
        return None
    
    def extract_paper_links(self, url):
        """
        从页面中提取论文链接和元数据
        
        Args:
            url: 会议页面URL
            
        Returns:
            论文信息列表，每个元素包含title, pdf_url, authors等信息
        """
        papers = []
        
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找所有可能包含论文链接的元素
            # USENIX Security的页面结构可能包含：
            # 1. 直接链接到PDF的<a>标签
            # 2. 论文标题链接，点击后进入详情页，再下载PDF
            
            # 方法1: 查找直接链接到PDF的链接
            pdf_links = soup.find_all('a', href=re.compile(r'\.pdf$', re.I))
            for link in pdf_links:
                pdf_url = link.get('href', '')
                if pdf_url:
                    if not pdf_url.startswith('http'):
                        pdf_url = urljoin(self.BASE_URL, pdf_url)
                    
                    # 尝试获取论文标题
                    title = link.text.strip()
                    if not title:
                        # 尝试从父元素获取标题
                        parent = link.find_parent(['div', 'li', 'td', 'article'])
                        if parent:
                            title_elem = parent.find(['h3', 'h4', 'strong', 'span'], 
                                                    class_=re.compile(r'title|paper', re.I))
                            if title_elem:
                                title = title_elem.get_text(strip=True)
                    
                    if title:
                        papers.append({
                            'title': title,
                            'pdf_url': pdf_url,
                            'authors': '',
                            'session': ''
                        })
            
            # 方法2: 查找论文标题链接，然后访问详情页
            paper_links = soup.find_all('a', href=re.compile(r'/conference/usenixsecurity\d+/presentation/'))
            seen_presentation_urls = set()
            
            logger.info(f"找到 {len(paper_links)} 个presentation链接，开始处理...")
            
            for idx, link in enumerate(paper_links):
                if idx > 0 and idx % 50 == 0:
                    logger.info(f"已处理 {idx}/{len(paper_links)} 个链接，找到 {len(papers)} 篇论文")
                href = link.get('href', '')
                if href in seen_presentation_urls:
                    continue
                seen_presentation_urls.add(href)
                
                paper_url = urljoin(self.BASE_URL, href)
                title = link.get_text(strip=True)
                
                # 如果标题为空，尝试从父元素获取
                if not title or len(title) < 10:
                    parent = link.find_parent(['li', 'div', 'article'])
                    if parent:
                        title_elem = parent.find(['h3', 'h4', 'strong', 'a'])
                        if title_elem:
                            title = title_elem.get_text(strip=True)
                
                if not title or len(title) < 10:
                    continue
                
                # 尝试从presentation URL推断PDF URL
                # USENIX Security的PDF可能格式为: /sites/default/files/sec{year}_paper_{slug}.pdf
                year_match = re.search(r'usenixsecurity(\d+)', href)
                if year_match:
                    year = year_match.group(1)
                    slug = href.split('/')[-1]
                    # 尝试多种可能的PDF URL格式
                    possible_pdf_urls = [
                        f"{self.BASE_URL}/sites/default/files/sec{year}_paper_{slug}.pdf",
                        f"{self.BASE_URL}/sites/default/files/{slug}.pdf",
                        f"{self.BASE_URL}/conference/usenixsecurity{year}/presentation/{slug}/paper.pdf",
                    ]
                    
                    # 先尝试这些可能的URL
                    pdf_found = False
                    for pdf_url in possible_pdf_urls:
                        try:
                            test_response = self.session.head(pdf_url, timeout=5, allow_redirects=True)
                            if test_response.status_code == 200 and 'pdf' in test_response.headers.get('Content-Type', '').lower():
                                papers.append({
                                    'title': title,
                                    'pdf_url': pdf_url,
                                    'authors': '',
                                    'session': ''
                                })
                                pdf_found = True
                                break
                        except:
                            continue
                    
                    # 如果直接URL不行，访问详情页
                    if not pdf_found:
                        try:
                            time.sleep(self.delay)
                            paper_response = self.session.get(paper_url, timeout=10)
                            if paper_response.status_code == 200:
                                paper_soup = BeautifulSoup(paper_response.text, 'html.parser')
                                
                                # 查找PDF链接
                                pdf_link = paper_soup.find('a', href=re.compile(r'\.pdf$', re.I))
                                if not pdf_link:
                                    # 尝试查找所有包含paper的链接
                                    all_links = paper_soup.find_all('a', href=True)
                                    for a_link in all_links:
                                        href_text = a_link.get('href', '')
                                        if 'paper' in href_text.lower() and '.pdf' in href_text.lower():
                                            pdf_link = a_link
                                            break
                                
                                if pdf_link:
                                    pdf_url = pdf_link.get('href', '')
                                    if not pdf_url.startswith('http'):
                                        pdf_url = urljoin(self.BASE_URL, pdf_url)
                                    
                                    # 提取作者信息
                                    authors = ''
                                    authors_elem = paper_soup.find(['div', 'p'], class_=re.compile(r'author', re.I))
                                    if authors_elem:
                                        authors = authors_elem.get_text(strip=True)
                                    
                                    papers.append({
                                        'title': title,
                                        'pdf_url': pdf_url,
                                        'authors': authors,
                                        'session': ''
                                    })
                        except Exception as e:
                            logger.debug(f"访问论文详情页失败 {paper_url}: {e}")
                            continue
            
            # 方法3: 查找包含"Download PDF"或类似文本的链接
            download_links = soup.find_all('a', string=re.compile(r'(pdf|download)', re.I))
            for link in download_links:
                href = link.get('href', '')
                if '.pdf' in href.lower():
                    pdf_url = href if href.startswith('http') else urljoin(self.BASE_URL, href)
                    title = link.find_previous(['h3', 'h4', 'strong', 'a'])
                    if title:
                        title = title.get_text(strip=True)
                    else:
                        title = f"paper_{len(papers)+1}"
                    
                    papers.append({
                        'title': title,
                        'pdf_url': pdf_url,
                        'authors': '',
                        'session': ''
                    })
            
            # 去重
            seen_urls = set()
            unique_papers = []
            for paper in papers:
                if paper['pdf_url'] not in seen_urls:
                    seen_urls.add(paper['pdf_url'])
                    unique_papers.append(paper)
            
            logger.info(f"从 {url} 提取到 {len(unique_papers)} 篇论文")
            return unique_papers
            
        except Exception as e:
            logger.error(f"提取论文链接失败: {e}")
            return []
    
    def save_metadata(self, papers, year):
        """
        保存论文元数据到文件
        
        Args:
            papers: 论文信息列表
            year: 年份
        """
        formats = []
        if self.metadata_format == 'all':
            formats = ['txt', 'csv', 'json']
        else:
            formats = [self.metadata_format]
        
        base_path = self.base_dir / str(year)
        
        for fmt in formats:
            if fmt == 'txt':
                # TXT格式（向后兼容）
                metadata_file = base_path / "metadata.txt"
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    f.write(f"USENIX Security {year} Papers\n")
                    f.write(f"=" * 50 + "\n\n")
                    for paper in papers:
                        f.write(f"Title: {paper['title']}\n")
                        f.write(f"PDF URL: {paper['pdf_url']}\n")
                        if paper.get('authors'):
                            f.write(f"Authors: {paper['authors']}\n")
                        if paper.get('session'):
                            f.write(f"Session: {paper['session']}\n")
                        f.write("\n")
            
            elif fmt == 'csv':
                # CSV格式（标准格式）
                metadata_file = base_path / "metadata.csv"
                with open(metadata_file, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.writer(f)
                    # 写入表头
                    writer.writerow(['Title', 'Authors', 'PDF URL', 'Session'])
                    # 写入数据
                    for paper in papers:
                        writer.writerow([
                            paper['title'],
                            paper.get('authors', ''),
                            paper['pdf_url'],
                            paper.get('session', '')
                        ])
            
            elif fmt == 'json':
                # JSON格式（结构化数据）
                metadata_file = base_path / "metadata.json"
                metadata = {
                    'conference': 'USENIX Security',
                    'year': year,
                    'total_papers': len(papers),
                    'papers': papers
                }
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        logger.info(f"元数据已保存为: {', '.join(formats)} 格式")
    
    def download_paper(self, paper_info, save_path, session=None, max_retries=3):
        """
        下载单篇论文（带重试机制）
        
        Args:
            paper_info: 论文信息字典
            save_path: 保存路径
            session: requests Session对象，如果为None则使用self.session
            max_retries: 最大重试次数
            
        Returns:
            是否下载成功
        """
        # 下载前再次检查文件是否存在（防止并发时重复下载）
        if save_path.exists() and save_path.stat().st_size > 1000:
            return True
        
        # 使用传入的session或创建新的
        if session is None:
            session = self.session
        
        pdf_url = paper_info['pdf_url']
        
        # 重试循环
        for attempt in range(max_retries):
            temp_path = save_path.with_suffix('.tmp')
            
            try:
                # 指数退避：第1次立即，第2次等1秒，第3次等2秒
                if attempt > 0:
                    wait_time = min(2 ** (attempt - 1), 5)  # 最多等待5秒
                    logger.info(f"重试下载 (第{attempt + 1}/{max_retries}次): {pdf_url[:80]}...")
                    time.sleep(wait_time)
                
                # 设置更长的超时时间，并允许重定向
                response = session.get(
                    pdf_url, 
                    timeout=(10, 60),  # (连接超时, 读取超时)
                    stream=True,
                    allow_redirects=True
                )
                response.raise_for_status()
                
                # 验证Content-Type
                content_type = response.headers.get('Content-Type', '').lower()
                if 'pdf' not in content_type and 'octet-stream' not in content_type:
                    # 读取前几个字节验证
                    content_preview = next(response.iter_content(chunk_size=1024), None)
                    if not content_preview or content_preview[:4] != b'%PDF':
                        # 检查是否是HTML错误页面
                        if content_preview:
                            preview_str = content_preview[:200].decode('utf-8', errors='ignore').lower()
                            if '<html' in preview_str or '<!doctype' in preview_str:
                                logger.warning(f"下载的不是PDF文件（HTML响应）: {pdf_url}")
                                if attempt < max_retries - 1:
                                    continue
                                return False
                        logger.warning(f"文件可能不是PDF: {pdf_url}")
                
                # 保存文件（使用临时文件名，避免并发冲突）
                with open(temp_path, 'wb') as f:
                    # 如果已经读取了预览内容，先写入
                    if 'content_preview' in locals() and content_preview:
                        f.write(content_preview)
                        # 继续下载剩余内容
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    else:
                        # 直接下载
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                
                # 验证文件大小和内容
                file_size = temp_path.stat().st_size
                if file_size < 1000:  # 小于1KB可能是错误页面
                    logger.warning(f"下载的文件过小 ({file_size} bytes): {save_path}")
                    temp_path.unlink()
                    if attempt < max_retries - 1:
                        continue
                    return False
                
                # 再次验证文件开头是否为PDF
                with open(temp_path, 'rb') as f:
                    file_start = f.read(4)
                    if file_start != b'%PDF':
                        logger.error(f"保存的文件不是有效的PDF: {save_path}")
                        temp_path.unlink()
                        if attempt < max_retries - 1:
                            continue
                        return False
                
                # 原子性重命名
                temp_path.replace(save_path)
                return True
                
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, 
                    requests.exceptions.ChunkedEncodingError) as e:
                # 网络相关错误，可以重试
                error_type = type(e).__name__
                if attempt < max_retries - 1:
                    logger.warning(f"下载失败 ({error_type}): {pdf_url[:80]}...，将重试")
                    # 清理临时文件
                    if temp_path.exists():
                        temp_path.unlink()
                    continue
                else:
                    logger.error(f"下载论文失败（已重试{max_retries}次） {pdf_url}: {e}")
                    if temp_path.exists():
                        temp_path.unlink()
                    return False
                    
            except requests.exceptions.HTTPError as e:
                # HTTP错误（如404, 403），通常不应该重试
                logger.error(f"HTTP错误 {e.response.status_code}: {pdf_url}")
                if temp_path.exists():
                    temp_path.unlink()
                return False
                
            except Exception as e:
                # 其他错误
                logger.error(f"下载论文失败 {pdf_url}: {e}")
                if temp_path.exists():
                    temp_path.unlink()
                if attempt < max_retries - 1:
                    continue
                return False
        
        return False
    
    def _download_worker(self, paper_info, save_path, index, total):
        """
        并发下载工作线程
        
        Args:
            paper_info: 论文信息字典
            save_path: 保存路径
            index: 论文索引
            total: 总论文数
            
        Returns:
            (success, paper_info, index)
        """
        # 创建独立的session避免并发冲突
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        title = paper_info['title']
        filename = save_path.name
        
        # 检查文件是否已存在
        if save_path.exists():
            with self.download_lock:
                self.downloaded_count += 1
            logger.info(f"[{index}/{total}] 跳过已存在: {filename}")
            return (True, paper_info, index)
        
        logger.info(f"[{index}/{total}] 下载: {title[:60]}...")
        
        success = self.download_paper(paper_info, save_path, session=session)
        
        with self.download_lock:
            if success:
                self.downloaded_count += 1
                logger.info(f"[{index}/{total}] ✓ 下载成功: {filename}")
            else:
                self.failed_count += 1
                logger.error(f"[{index}/{total}] ✗ 下载失败: {filename}")
        
        session.close()
        return (success, paper_info, index)
    
    def crawl_year(self, year):
        """
        爬取指定年份的所有论文
        
        Args:
            year: 会议年份
            
        Returns:
            下载的论文数量
        """
        logger.info(f"开始爬取 {year} 年 USENIX Security 论文")
        
        # 获取论文页面URL
        papers_url = self.get_papers_url(year)
        if not papers_url:
            logger.warning(f"未找到 {year} 年的会议页面")
            return 0
        
        # 提取论文链接
        papers = self.extract_paper_links(papers_url)
        if not papers:
            logger.warning(f"{year} 年未找到论文")
            return 0
        
        # 创建保存目录
        save_dir = self.base_dir / str(year) / "papers"
        save_dir.mkdir(parents=True, exist_ok=True)
        
        # 重置计数器
        self.downloaded_count = 0
        self.failed_count = 0
        
        # 准备下载任务：过滤已存在的文件，准备需要下载的论文
        download_tasks = []
        skipped = 0
        
        for i, paper in enumerate(papers, 1):
            title = paper['title']
            safe_title = self.sanitize_filename(title)
            filename = f"{safe_title}.pdf"
            save_path = save_dir / filename
            
            # 检查文件是否已存在
            if save_path.exists() and save_path.stat().st_size > 1000:
                skipped += 1
                continue
            
            download_tasks.append((paper, save_path, i, len(papers)))
        
        logger.info(f"需要下载: {len(download_tasks)} 篇, 已存在: {skipped} 篇, 总计: {len(papers)} 篇")
        
        # 使用线程池并发下载
        if download_tasks:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # 提交所有下载任务
                future_to_task = {
                    executor.submit(self._download_worker, paper, path, idx, total): (paper, path, idx)
                    for paper, path, idx, total in download_tasks
                }
                
                # 等待所有任务完成
                for future in as_completed(future_to_task):
                    try:
                        future.result()
                    except Exception as e:
                        logger.error(f"下载任务异常: {e}")
        
        downloaded = self.downloaded_count + skipped
        failed = self.failed_count
        
        # 保存论文元数据
        self.save_metadata(papers, year)
        
        logger.info(f"{year} 年完成: 成功 {downloaded}, 失败 {failed}, 总计 {len(papers)}")
        return downloaded
    
    def crawl(self, years=None):
        """
        爬取指定年份的论文
        
        Args:
            years: 年份列表，如果为None则爬取所有可用年份
        """
        if years is None:
            years = self.get_conference_years()
        
        logger.info(f"开始爬取 USENIX Security 论文，年份: {years}")
        
        total_downloaded = 0
        for year in years:
            try:
                count = self.crawl_year(year)
                total_downloaded += count
            except Exception as e:
                logger.error(f"爬取 {year} 年失败: {e}")
                continue
        
        logger.info(f"全部完成！共下载 {total_downloaded} 篇论文")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='USENIX Security 论文爬虫')
    parser.add_argument('-y', '--years', nargs='+', type=int, 
                       help='要下载的年份列表，例如: -y 2023 2024')
    parser.add_argument('-d', '--dir', default='USENIX_Security',
                       help='保存目录（默认: USENIX_Security）')
    parser.add_argument('--delay', type=float, default=1.0,
                       help='请求之间的延迟秒数（默认: 1.0，并发下载时此参数影响较小）')
    parser.add_argument('--workers', type=int, default=5,
                       help='并发下载的最大线程数（默认: 5）')
    parser.add_argument('--format', choices=['txt', 'csv', 'json', 'all'], default='csv',
                       help='元数据保存格式（默认: csv，可选: txt, csv, json, all）')
    
    args = parser.parse_args()
    
    crawler = USENIXSecurityCrawler(base_dir=args.dir, delay=args.delay, max_workers=args.workers,
                                    metadata_format=args.format)
    crawler.crawl(years=args.years)


if __name__ == '__main__':
    main()

