#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NDSS (Network and Distributed System Security Symposium) 论文爬虫
下载NDSS会议的论文PDF，并按照官方结构组织目录

目录结构：
NDSS/
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
        logging.FileHandler(logs_dir / 'ndss_download.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class NDSSCrawler:
    """NDSS会议论文爬虫"""
    
    BASE_URL = "https://www.ndss-symposium.org"
    
    def __init__(self, base_dir="NDSS", delay=1.0, max_workers=5, metadata_format='csv'):
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
        # NDSS通常从1994年开始，我们可以尝试获取可用年份
        current_year = 2024
        years = list(range(1994, current_year + 1))
        return years
    
    def get_papers_url(self, year):
        """
        获取指定年份的论文页面URL
        
        Args:
            year: 会议年份
            
        Returns:
            论文页面URL列表（可能多个页面）
        """
        # NDSS的URL格式通常是：
        # https://www.ndss-symposium.org/ndss{year}/accepted-papers/
        # 或 https://www.ndss-symposium.org/ndss{year}/program/
        
        urls_to_try = [
            f"{self.BASE_URL}/ndss{year}/accepted-papers/",
            f"{self.BASE_URL}/ndss{year}/program/",
            f"{self.BASE_URL}/ndss{year}/",
            f"{self.BASE_URL}/ndss{year}/papers/",
        ]
        
        valid_urls = []
        for url in urls_to_try:
            try:
                response = self.session.get(url, timeout=10)
                if response.status_code == 200:
                    logger.info(f"找到{year}年会议页面: {url}")
                    valid_urls.append(url)
            except Exception as e:
                logger.debug(f"尝试{url}失败: {e}")
                continue
        
        return valid_urls if valid_urls else None
    
    def extract_paper_links(self, urls):
        """
        从页面中提取论文链接和元数据
        
        Args:
            urls: 会议页面URL列表
            
        Returns:
            论文信息列表，每个元素包含title, pdf_url, authors等信息
        """
        papers = []
        seen_urls = set()
        seen_paper_slugs = set()
        
        # 从URL中提取年份
        year = None
        for url in urls:
            year_match = re.search(r'ndss(\d{4})', url)
            if year_match:
                year = year_match.group(1)
                break
        
        for url in urls:
            try:
                response = self.session.get(url, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 方法1: 查找指向论文详情页的链接 (/ndss-paper/xxx/)
                paper_detail_links = soup.find_all('a', href=re.compile(r'/ndss-paper/'))
                logger.info(f"从 {url} 找到 {len(paper_detail_links)} 个论文详情链接")
                
                for detail_link in paper_detail_links:
                    detail_href = detail_link.get('href', '')
                    if not detail_href or detail_href in seen_paper_slugs:
                        continue
                    
                    # 提取论文slug
                    slug_match = re.search(r'/ndss-paper/([^/]+)/?', detail_href)
                    if not slug_match:
                        continue
                    
                    slug = slug_match.group(1)
                    if slug in seen_paper_slugs:
                        continue
                    seen_paper_slugs.add(slug)
                    
                    # 构建详情页URL
                    if not detail_href.startswith('http'):
                        detail_url = urljoin(self.BASE_URL, detail_href)
                    else:
                        detail_url = detail_href
                    
                    # 访问详情页获取PDF链接和标题
                    title = None
                    pdf_url = None
                    authors = ''
                    
                    try:
                        time.sleep(self.delay * 0.5)  # 使用较短的延迟
                        detail_response = self.session.get(detail_url, timeout=10)
                        if detail_response.status_code == 200:
                            detail_soup = BeautifulSoup(detail_response.text, 'html.parser')
                            
                            # 首先获取标题（从详情页）
                            title_elem = detail_soup.find(['h1', 'h2', 'h3'])
                            if title_elem:
                                title = title_elem.get_text(strip=True)
                            
                            # 如果标题还是没找到，尝试从其他位置
                            if not title or len(title) < 10:
                                # 尝试查找包含title的div或class
                                title_div = detail_soup.find(['div', 'span'], class_=re.compile(r'title', re.I))
                                if title_div:
                                    title = title_div.get_text(strip=True)
                            
                            # 如果还是没找到，尝试从URL的slug推断
                            if not title or len(title) < 10:
                                # 从slug推断标题（将连字符转换为空格，首字母大写）
                                title = slug.replace('-', ' ').title()
                            
                            # 查找PDF链接
                            pdf_link = detail_soup.find('a', href=re.compile(r'\.pdf$', re.I))
                            if pdf_link:
                                pdf_url = pdf_link.get('href', '')
                                if not pdf_url.startswith('http'):
                                    pdf_url = urljoin(self.BASE_URL, pdf_url)
                                
                                # 只保存论文PDF，跳过slides
                                if 'slide' in pdf_url.lower():
                                    # 查找其他PDF链接
                                    all_pdf_links = detail_soup.find_all('a', href=re.compile(r'\.pdf$', re.I))
                                    for alt_pdf in all_pdf_links:
                                        alt_href = alt_pdf.get('href', '')
                                        if 'paper' in alt_href.lower() and 'slide' not in alt_href.lower():
                                            pdf_url = alt_href if alt_href.startswith('http') else urljoin(self.BASE_URL, alt_href)
                                            break
                                
                            # 提取作者
                            authors_elem = detail_soup.find(['div', 'p'], class_=re.compile(r'author', re.I))
                            if authors_elem:
                                authors = authors_elem.get_text(strip=True)
                            
                            # 如果找到了PDF和标题，添加到列表
                            if pdf_url and title and len(title) > 10:
                                if pdf_url not in seen_urls:
                                    seen_urls.add(pdf_url)
                                    papers.append({
                                        'title': title,
                                        'pdf_url': pdf_url,
                                        'authors': authors,
                                        'session': ''
                                    })
                                    logger.debug(f"提取论文: {title[:60]}...")
                    except Exception as e:
                        logger.debug(f"访问论文详情页失败 {detail_url}: {e}")
                        continue
                
                # 方法2: 查找直接链接到PDF的链接（备用方法）
                pdf_links = soup.find_all('a', href=re.compile(r'\.pdf$', re.I))
                for link in pdf_links:
                    pdf_url = link.get('href', '')
                    if pdf_url and pdf_url not in seen_urls:
                        seen_urls.add(pdf_url)
                        
                        if not pdf_url.startswith('http'):
                            pdf_url = urljoin(self.BASE_URL, pdf_url)
                        
                        # 尝试获取论文标题
                        title = link.text.strip()
                        if not title or title.lower() in ['pdf', 'download', '[pdf]']:
                            # 尝试从父元素获取标题
                            parent = link.find_parent(['div', 'li', 'article', 'section', 'tr'])
                            if parent:
                                # 查找标题元素
                                title_elem = parent.find(['h3', 'h4', 'h5', 'strong', 'a', 'span'],
                                                         class_=re.compile(r'title|paper', re.I))
                                if title_elem:
                                    title = title_elem.get_text(strip=True)
                                else:
                                    # 尝试查找所有文本，提取标题
                                    text = parent.get_text(strip=True)
                                    if text:
                                        # 提取第一行作为标题
                                        title = text.split('\n')[0].strip()
                                        if len(title) > 200:
                                            title = title[:200]
                        
                        if not title:
                            title = f"paper_{len(papers)+1}"
                        
                        papers.append({
                            'title': title,
                            'pdf_url': pdf_url,
                            'authors': '',
                            'session': ''
                        })
                
                # 方法2: 查找论文列表项
                paper_items = soup.find_all(['li', 'div', 'tr'], 
                                           class_=re.compile(r'paper|accepted', re.I))
                for item in paper_items:
                    # 查找PDF链接
                    pdf_link = item.find('a', href=re.compile(r'\.pdf$', re.I))
                    if pdf_link:
                        pdf_url = pdf_link.get('href', '')
                        if pdf_url and pdf_url not in seen_urls:
                            seen_urls.add(pdf_url)
                            
                            if not pdf_url.startswith('http'):
                                pdf_url = urljoin(self.BASE_URL, pdf_url)
                            
                            # 提取标题
                            title_elem = item.find(['h3', 'h4', 'h5', 'strong', 'a'])
                            if title_elem:
                                title = title_elem.get_text(strip=True)
                            else:
                                title = item.get_text(strip=True).split('\n')[0]
                            
                            # 提取作者
                            authors = ''
                            authors_elem = item.find(['div', 'span', 'p'], 
                                                    class_=re.compile(r'author', re.I))
                            if authors_elem:
                                authors = authors_elem.get_text(strip=True)
                            
                            papers.append({
                                'title': title,
                                'pdf_url': pdf_url,
                                'authors': authors,
                                'session': ''
                            })
                
                # 方法3: 查找包含"PDF"文本的链接
                pdf_text_links = soup.find_all('a', string=re.compile(r'\[?PDF\]?', re.I))
                for link in pdf_text_links:
                    href = link.get('href', '')
                    if '.pdf' in href.lower():
                        pdf_url = href if href.startswith('http') else urljoin(self.BASE_URL, href)
                        if pdf_url not in seen_urls:
                            seen_urls.add(pdf_url)
                            
                            # 查找标题
                            title = ''
                            parent = link.find_parent(['div', 'li', 'tr', 'article'])
                            if parent:
                                title_elem = parent.find(['h3', 'h4', 'h5', 'strong'])
                                if title_elem:
                                    title = title_elem.get_text(strip=True)
                            
                            if not title:
                                title = f"paper_{len(papers)+1}"
                            
                            papers.append({
                                'title': title,
                                'pdf_url': pdf_url,
                                'authors': '',
                                'session': ''
                            })
                
                # 方法4: 查找表格中的论文（NDSS有时用表格展示）
                tables = soup.find_all('table')
                for table in tables:
                    rows = table.find_all('tr')
                    for row in rows:
                        pdf_link = row.find('a', href=re.compile(r'\.pdf$', re.I))
                        if pdf_link:
                            pdf_url = pdf_link.get('href', '')
                            if pdf_url and pdf_url not in seen_urls:
                                seen_urls.add(pdf_url)
                                
                                if not pdf_url.startswith('http'):
                                    pdf_url = urljoin(self.BASE_URL, pdf_url)
                                
                                # 从表格单元格提取标题和作者
                                cells = row.find_all(['td', 'th'])
                                title = ''
                                authors = ''
                                
                                for cell in cells:
                                    text = cell.get_text(strip=True)
                                    if not title and text and len(text) > 10:
                                        title = text
                                    elif not authors and 'author' in cell.get('class', []):
                                        authors = text
                                
                                if not title:
                                    title = f"paper_{len(papers)+1}"
                                
                                papers.append({
                                    'title': title,
                                    'pdf_url': pdf_url,
                                    'authors': authors,
                                    'session': ''
                                })
                
            except Exception as e:
                logger.error(f"提取论文链接失败 {url}: {e}")
                continue
        
        # 去重
        unique_papers = []
        seen_titles = set()
        for paper in papers:
            # 使用URL和标题组合去重
            key = (paper['pdf_url'], paper['title'].lower())
            if key not in seen_titles:
                seen_titles.add(key)
                unique_papers.append(paper)
        
        logger.info(f"提取到 {len(unique_papers)} 篇论文")
        return unique_papers
    
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
                    f.write(f"NDSS {year} Papers\n")
                    f.write(f"=" * 50 + "\n\n")
                    for paper in papers:
                        f.write(f"Title: {paper['title']}\n")
                        f.write(f"PDF URL: {paper['pdf_url']}\n")
                        if paper['authors']:
                            f.write(f"Authors: {paper['authors']}\n")
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
                    'conference': 'NDSS',
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
        logger.info(f"开始爬取 {year} 年 NDSS 论文")
        
        # 获取论文页面URL
        papers_urls = self.get_papers_url(year)
        if not papers_urls:
            logger.warning(f"未找到 {year} 年的会议页面")
            return 0
        
        # 提取论文链接
        papers = self.extract_paper_links(papers_urls)
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
        
        logger.info(f"开始爬取 NDSS 论文，年份: {years}")
        
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
    
    parser = argparse.ArgumentParser(description='NDSS 论文爬虫')
    parser.add_argument('-y', '--years', nargs='+', type=int, 
                       help='要下载的年份列表，例如: -y 2023 2024')
    parser.add_argument('-d', '--dir', default='NDSS',
                       help='保存目录（默认: NDSS）')
    parser.add_argument('--delay', type=float, default=1.0,
                       help='请求之间的延迟秒数（默认: 1.0，并发下载时此参数影响较小）')
    parser.add_argument('--workers', type=int, default=5,
                       help='并发下载的最大线程数（默认: 5）')
    parser.add_argument('--format', choices=['txt', 'csv', 'json', 'all'], default='csv',
                       help='元数据保存格式（默认: csv，可选: txt, csv, json, all）')
    
    args = parser.parse_args()
    
    crawler = NDSSCrawler(base_dir=args.dir, delay=args.delay, max_workers=args.workers, 
                          metadata_format=args.format)
    crawler.crawl(years=args.years)


if __name__ == '__main__':
    main()

