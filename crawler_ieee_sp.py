#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IEEE S&P (IEEE Symposium on Security and Privacy) 论文爬虫
从 IEEE Computer Society Digital Library (CSDL) 下载论文PDF

开放获取政策说明：
- 论文被接收后立即在 CSDL 开放获取
- 会议结束后进入1年付费墙
- 1年后再次开放获取

因此：2023年及更早的论文应该都是免费开放获取的

目录结构：
IEEE_SP/
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
from urllib.parse import urljoin, urlparse, quote
from bs4 import BeautifulSoup
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import csv
import json

# 配置日志
logs_dir = Path('logs')
logs_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(logs_dir / 'ieee_sp_download.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class IEEESPCrawler:
    """IEEE S&P 会议论文爬虫 - 基于IEEE Xplore REST API"""

    # IEEE Xplore Base URL
    XPLORE_BASE = "https://ieeexplore.ieee.org"

    # IEEE Computer Society Digital Library
    CSDL_BASE = "https://www.computer.org"

    # IEEE S&P Proceedings ID in CSDL
    SP_PROCEEDINGS_ID = "1000646"

    # 年度Proceedings的IEEE Xplore punumber (proceeding number)
    YEAR_PROCEEDING_IDS = {
        2025: "10919321",  # May need update
        2024: "10646615",
        2023: "10179215",
        2022: "9833550",
        2021: "9519381",
        2020: "9144328",
        2019: "8835275",
        2018: "8418567",
    }

    def __init__(self, base_dir="IEEE_SP", delay=1.0, max_workers=5, metadata_format='csv'):
        """
        初始化爬虫

        Args:
            base_dir: 保存论文的基础目录
            delay: 请求之间的延迟（秒）
            max_workers: 并发下载的最大线程数
            metadata_format: 元数据保存格式，可选: 'txt', 'csv', 'json', 'all'
        """
        self.base_dir = Path(base_dir)
        self.delay = delay
        self.max_workers = max_workers
        self.metadata_format = metadata_format
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
        })
        self.download_lock = Lock()
        self.downloaded_count = 0
        self.failed_count = 0

    def sanitize_filename(self, filename):
        """
        清理文件名，移除非法字符
        """
        # 移除非法字符
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # 替换特殊字符
        filename = filename.replace('\n', ' ').replace('\r', ' ')
        # 移除多余空格
        filename = re.sub(r'\s+', ' ', filename).strip()
        # 限制长度
        if len(filename) > 200:
            filename = filename[:200]
        return filename

    def get_ieee_security_program_url(self, year):
        """
        获取IEEE Security官网的program页面URL

        Args:
            year: 会议年份

        Returns:
            Program页面URL列表
        """
        urls = []

        # 新格式 (2023+)
        urls.append(f"https://sp{year}.ieee-security.org/program-papers.html")
        urls.append(f"https://sp{year}.ieee-security.org/accepted-papers.html")

        # 旧格式 (2022及更早)
        urls.append(f"https://www.ieee-security.org/TC/SP{year}/program-papers.html")
        urls.append(f"https://www.ieee-security.org/TC/SP{year}/program.html")

        return urls

    def extract_papers_from_xplore_api(self, year):
        """
        从IEEE Xplore REST API提取论文列表

        Args:
            year: 会议年份

        Returns:
            论文信息列表
        """
        papers = []

        # 获取该年份的proceeding number
        punumber = self.YEAR_PROCEEDING_IDS.get(year)
        if not punumber:
            logger.warning(f"未知年份 {year} 的proceeding ID，尝试搜索...")
            return self._search_papers_by_year(year)

        logger.info(f"从IEEE Xplore API获取 {year} 年论文列表 (punumber={punumber})...")

        api_url = f"{self.XPLORE_BASE}/rest/search"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Origin': self.XPLORE_BASE,
            'Referer': f'{self.XPLORE_BASE}/xpl/conhome/{punumber}/proceeding',
        }

        page = 1
        rows_per_page = 100
        total_records = 0

        while True:
            payload = {
                'punumber': punumber,
                'rowsPerPage': rows_per_page,
                'pageNumber': page,
            }

            try:
                response = self.session.post(api_url, json=payload, headers=headers, timeout=60)

                if response.status_code != 200:
                    logger.warning(f"IEEE Xplore API返回状态码 {response.status_code}")
                    break

                data = response.json()
                total_records = data.get('totalRecords', 0)
                records = data.get('records', [])

                if page == 1:
                    logger.info(f"IEEE Xplore API返回 {total_records} 篇论文")

                if not records:
                    break

                for record in records:
                    title = record.get('articleTitle', '')
                    if not title:
                        continue

                    article_number = record.get('articleNumber', '')

                    # 提取作者
                    authors = []
                    for author in record.get('authors', []):
                        author_name = author.get('preferredName', '') or author.get('normalizedName', '')
                        if author_name:
                            authors.append(author_name)
                    authors_str = ', '.join(authors)

                    # 构建PDF URL - 使用IEEE Xplore的stamp链接
                    pdf_url = ''
                    if article_number:
                        pdf_url = f"{self.XPLORE_BASE}/stamp/stamp.jsp?tp=&arnumber={article_number}"

                    # 检查是否是开放获取
                    is_open_access = record.get('isOpenAccess', False)

                    papers.append({
                        'title': title,
                        'authors': authors_str,
                        'pdf_url': pdf_url,
                        'article_number': article_number,
                        'doi': record.get('doi', ''),
                        'abstract': record.get('abstract', ''),
                        'is_open_access': is_open_access,
                    })

                # 检查是否还有更多页
                if len(papers) >= total_records or len(records) < rows_per_page:
                    break

                page += 1
                time.sleep(self.delay)

            except Exception as e:
                logger.error(f"IEEE Xplore API请求失败: {e}")
                break

        if papers:
            logger.info(f"从IEEE Xplore API获取到 {len(papers)} 篇论文")

        return papers

    def _search_papers_by_year(self, year):
        """
        通过搜索获取指定年份的论文

        Args:
            year: 会议年份

        Returns:
            论文信息列表
        """
        papers = []

        api_url = f"{self.XPLORE_BASE}/rest/search"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Origin': self.XPLORE_BASE,
        }

        search_query = f'"IEEE Symposium on Security and Privacy" AND year:{year}'

        payload = {
            'queryText': search_query,
            'rowsPerPage': 100,
            'pageNumber': 1,
        }

        try:
            response = self.session.post(api_url, json=payload, headers=headers, timeout=60)

            if response.status_code == 200:
                data = response.json()
                records = data.get('records', [])

                for record in records:
                    title = record.get('articleTitle', '')
                    if not title:
                        continue

                    article_number = record.get('articleNumber', '')
                    authors = []
                    for author in record.get('authors', []):
                        author_name = author.get('preferredName', '') or author.get('normalizedName', '')
                        if author_name:
                            authors.append(author_name)

                    pdf_url = ''
                    if article_number:
                        pdf_url = f"{self.XPLORE_BASE}/stamp/stamp.jsp?tp=&arnumber={article_number}"

                    papers.append({
                        'title': title,
                        'authors': ', '.join(authors),
                        'pdf_url': pdf_url,
                        'article_number': article_number,
                        'doi': record.get('doi', ''),
                        'abstract': record.get('abstract', ''),
                        'is_open_access': record.get('isOpenAccess', False),
                    })

        except Exception as e:
            logger.error(f"搜索论文失败: {e}")

        return papers

    def extract_papers_from_csdl_api(self, year):
        """
        从CSDL搜索API提取论文列表

        Args:
            year: 会议年份

        Returns:
            论文信息列表
        """
        papers = []

        # 尝试CSDL搜索API
        search_url = "https://www.computer.org/csdl/api/v1/search"

        try:
            logger.info(f"尝试从CSDL搜索API获取 {year} 年论文列表...")

            # 搜索参数
            params = {
                'q': f'proceedings:sp AND year:{year}',
                'rows': 200,
                'start': 0,
            }

            response = self.session.get(search_url, params=params, timeout=30)

            if response.status_code == 200:
                try:
                    data = response.json()
                    if 'response' in data and 'docs' in data['response']:
                        for doc in data['response']['docs']:
                            paper = {
                                'title': doc.get('title', ''),
                                'authors': ', '.join(doc.get('authors', [])),
                                'pdf_url': '',
                                'article_id': doc.get('id', ''),
                                'doi': doc.get('doi', ''),
                                'abstract': doc.get('abstract', ''),
                            }
                            # 构建PDF URL
                            if paper['article_id']:
                                paper['pdf_url'] = f"{self.CSDL_BASE}/csdl/pds/api/csdl/proceedings/download-article/{paper['article_id']}/pdf"
                            if paper['title']:
                                papers.append(paper)

                        if papers:
                            logger.info(f"从CSDL搜索API获取到 {len(papers)} 篇论文")
                            return papers
                except json.JSONDecodeError:
                    logger.debug("CSDL搜索API返回非JSON格式")

        except Exception as e:
            logger.debug(f"CSDL搜索API请求失败: {e}")

        return papers

    def extract_papers_from_csdl_page(self, year):
        """
        从CSDL proceedings页面提取论文列表

        Args:
            year: 会议年份

        Returns:
            论文信息列表
        """
        papers = []

        # CSDL proceedings页面URL
        proceedings_url = f"{self.CSDL_BASE}/csdl/proceedings/sp/{year}"

        try:
            logger.info(f"尝试从CSDL proceedings页面获取论文列表: {proceedings_url}")
            response = self.session.get(proceedings_url, timeout=30)

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')

                # 查找所有论文链接
                # CSDL页面结构: 论文链接格式为 /csdl/proceedings-article/sp/{year}/{id}/{hash}
                article_links = soup.find_all('a', href=re.compile(r'/csdl/proceedings-article/sp/\d+/'))

                seen_urls = set()
                for link in article_links:
                    href = link.get('href', '')
                    if href in seen_urls:
                        continue
                    seen_urls.add(href)

                    # 提取标题
                    title = link.get_text(strip=True)
                    if not title or len(title) < 10:
                        # 尝试从父元素获取
                        parent = link.find_parent(['div', 'li', 'article'])
                        if parent:
                            title_elem = parent.find(['h2', 'h3', 'h4', 'span'], class_=re.compile(r'title', re.I))
                            if title_elem:
                                title = title_elem.get_text(strip=True)

                    if not title or len(title) < 10:
                        continue

                    # 从URL提取article hash
                    match = re.search(r'/csdl/proceedings-article/sp/\d+/[^/]+/([^/]+)', href)
                    article_id = match.group(1) if match else ''

                    # 构建PDF URL
                    pdf_url = ''
                    if article_id:
                        pdf_url = f"{self.CSDL_BASE}/csdl/pds/api/csdl/proceedings/download-article/{article_id}/pdf"

                    # 提取作者
                    authors = ''
                    parent = link.find_parent(['div', 'li', 'article'])
                    if parent:
                        author_elem = parent.find(['span', 'div'], class_=re.compile(r'author', re.I))
                        if author_elem:
                            authors = author_elem.get_text(strip=True)

                    papers.append({
                        'title': title,
                        'authors': authors,
                        'pdf_url': pdf_url,
                        'article_id': article_id,
                        'doi': '',
                        'abstract': '',
                    })

                if papers:
                    logger.info(f"从CSDL页面获取到 {len(papers)} 篇论文")

        except Exception as e:
            logger.warning(f"CSDL页面请求失败: {e}")

        return papers

    def extract_papers_from_ieee_security(self, year):
        """
        从IEEE Security官网提取论文列表，然后构建CSDL下载链接

        Args:
            year: 会议年份

        Returns:
            论文信息列表
        """
        papers = []
        seen_titles = set()

        urls = self.get_ieee_security_program_url(year)

        for url in urls:
            try:
                logger.debug(f"尝试访问: {url}")
                response = self.session.get(url, timeout=30)

                if response.status_code != 200:
                    continue

                logger.info(f"成功访问: {url}")
                soup = BeautifulSoup(response.text, 'html.parser')

                # 方法1: 查找所有包含论文的链接（通常链接到CSDL或IEEE Xplore）
                paper_links = soup.find_all('a', href=re.compile(
                    r'computer\.org/csdl|ieeexplore\.ieee\.org/document', re.I))

                for link in paper_links:
                    href = link.get('href', '')

                    # 获取标题
                    title = link.get_text(strip=True)

                    # 如果链接文本不是标题，尝试从周围元素获取
                    if not title or len(title) < 15 or title.lower() in ['pdf', 'paper', '[pdf]']:
                        parent = link.find_parent(['tr', 'li', 'div', 'p', 'td'])
                        if parent:
                            # 查找标题元素
                            title_elem = parent.find(['strong', 'b', 'em', 'span'],
                                                      class_=re.compile(r'title|paper', re.I))
                            if title_elem:
                                title = title_elem.get_text(strip=True)
                            else:
                                # 尝试获取第一个粗体或强调文本
                                bold = parent.find(['strong', 'b'])
                                if bold:
                                    title = bold.get_text(strip=True)

                    if not title or len(title) < 15:
                        continue

                    # 跳过非论文标题
                    skip_keywords = ['session', 'keynote', 'welcome', 'break', 'lunch',
                                    'registration', 'closing', 'opening', 'panel']
                    if any(kw in title.lower() for kw in skip_keywords):
                        continue

                    title_key = title.lower()[:50]
                    if title_key in seen_titles:
                        continue
                    seen_titles.add(title_key)

                    # 提取PDF URL
                    pdf_url = ''
                    article_id = ''

                    if 'computer.org/csdl' in href:
                        # CSDL链接
                        match = re.search(r'/([^/]+)/pdf$', href)
                        if match:
                            article_id = match.group(1)
                            pdf_url = href
                        else:
                            match = re.search(r'/csdl/proceedings-article/sp/\d+/[^/]+/([^/]+)', href)
                            if match:
                                article_id = match.group(1)
                                pdf_url = f"{self.CSDL_BASE}/csdl/pds/api/csdl/proceedings/download-article/{article_id}/pdf"

                    elif 'ieeexplore.ieee.org' in href:
                        # IEEE Xplore链接 - 提取arnumber并构建CSDL URL
                        match = re.search(r'arnumber=(\d+)', href)
                        if not match:
                            match = re.search(r'/document/(\d+)', href)
                        if match:
                            # 暂时使用IEEE Xplore的stamp链接
                            arnumber = match.group(1)
                            pdf_url = f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={arnumber}"

                    # 提取作者
                    authors = ''
                    parent = link.find_parent(['tr', 'li', 'div', 'p'])
                    if parent:
                        # 查找作者信息（通常在标题后面，格式如 "Author1, Author2 (Affiliation)"）
                        author_elem = parent.find(['span', 'em', 'i', 'div'],
                                                   class_=re.compile(r'author', re.I))
                        if author_elem:
                            authors = author_elem.get_text(strip=True)
                        else:
                            # 尝试从文本中提取括号内的作者
                            text = parent.get_text()
                            # 移除标题部分
                            text = text.replace(title, '')
                            # 提取作者（通常格式为 "Name1, Name2 (Affiliation)" 或 "Name1 and Name2"）
                            author_match = re.search(r'^[,\s]*([A-Z][^()\[\]<>]{10,200})', text.strip())
                            if author_match:
                                authors = author_match.group(1).strip()

                    papers.append({
                        'title': title,
                        'authors': authors,
                        'pdf_url': pdf_url,
                        'article_id': article_id,
                        'doi': '',
                        'abstract': '',
                    })

                # 方法2: 如果没有找到带链接的论文，查找所有标题
                if not papers:
                    # 查找所有可能的论文标题（通常是粗体或特定class）
                    title_elements = soup.find_all(['strong', 'b', 'h3', 'h4', 'td'],
                                                    class_=re.compile(r'title|paper', re.I))
                    title_elements += soup.find_all(['strong', 'b'],
                                                     string=lambda s: s and len(s) > 20)

                    for elem in title_elements:
                        title = elem.get_text(strip=True)

                        if not title or len(title) < 15:
                            continue

                        # 跳过非论文
                        skip_keywords = ['session', 'keynote', 'welcome', 'break', 'lunch',
                                        'registration', 'closing', 'opening', 'panel']
                        if any(kw in title.lower() for kw in skip_keywords):
                            continue

                        title_key = title.lower()[:50]
                        if title_key in seen_titles:
                            continue
                        seen_titles.add(title_key)

                        # 在同一行或父元素中查找PDF链接
                        pdf_url = ''
                        parent = elem.find_parent(['tr', 'li', 'div', 'p'])
                        if parent:
                            pdf_link = parent.find('a', href=re.compile(
                                r'\.pdf|computer\.org|ieeexplore', re.I))
                            if pdf_link:
                                href = pdf_link.get('href', '')
                                if not href.startswith('http'):
                                    href = urljoin(url, href)

                                if 'computer.org/csdl' in href:
                                    match = re.search(r'/([^/]+)/pdf$', href)
                                    if match:
                                        pdf_url = href
                                    else:
                                        match = re.search(r'/csdl/proceedings-article/sp/\d+/[^/]+/([^/]+)', href)
                                        if match:
                                            article_id = match.group(1)
                                            pdf_url = f"{self.CSDL_BASE}/csdl/pds/api/csdl/proceedings/download-article/{article_id}/pdf"
                                elif 'ieeexplore.ieee.org' in href:
                                    match = re.search(r'arnumber=(\d+)|/document/(\d+)', href)
                                    if match:
                                        arnumber = match.group(1) or match.group(2)
                                        pdf_url = f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={arnumber}"
                                elif href.endswith('.pdf'):
                                    pdf_url = href

                        papers.append({
                            'title': title,
                            'authors': '',
                            'pdf_url': pdf_url,
                            'article_id': '',
                            'doi': '',
                            'abstract': '',
                        })

                if papers:
                    logger.info(f"从 {url} 获取到 {len(papers)} 篇论文")
                    break

            except Exception as e:
                logger.debug(f"访问 {url} 失败: {e}")
                continue

        return papers

    def extract_papers(self, year):
        """
        提取指定年份的论文列表（综合多种方法）

        Args:
            year: 会议年份

        Returns:
            论文信息列表
        """
        # 方法1: 优先使用IEEE Xplore REST API（最可靠）
        papers = self.extract_papers_from_xplore_api(year)
        if papers:
            return papers

        # 方法2: 尝试CSDL API
        papers = self.extract_papers_from_csdl_api(year)
        if papers:
            return papers

        # 方法3: 尝试CSDL页面
        papers = self.extract_papers_from_csdl_page(year)
        if papers:
            return papers

        # 方法4: 从IEEE Security官网获取
        papers = self.extract_papers_from_ieee_security(year)
        if papers:
            return papers

        logger.warning(f"无法获取 {year} 年的论文列表")
        return []

    def _get_pdf_url_from_stamp(self, article_number, session):
        """
        从stamp页面获取实际的PDF URL

        Args:
            article_number: IEEE文章编号
            session: requests Session

        Returns:
            PDF URL或None
        """
        stamp_url = f"{self.XPLORE_BASE}/stamp/stamp.jsp?tp=&arnumber={article_number}"

        try:
            response = session.get(stamp_url, timeout=30, allow_redirects=True)

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')

                # 查找iframe中的PDF URL
                iframe = soup.find('iframe', src=True)
                if iframe:
                    src = iframe.get('src', '')
                    if 'getPDF' in src or '.pdf' in src:
                        if not src.startswith('http'):
                            src = urljoin(self.XPLORE_BASE, src)
                        return src

                # 查找meta refresh
                meta = soup.find('meta', {'http-equiv': 'refresh'})
                if meta:
                    content = meta.get('content', '')
                    url_match = re.search(r'url=(.+)', content, re.I)
                    if url_match:
                        redirect_url = url_match.group(1)
                        if not redirect_url.startswith('http'):
                            redirect_url = urljoin(self.XPLORE_BASE, redirect_url)
                        return redirect_url

                # 查找直接的PDF链接
                pdf_link = soup.find('a', href=re.compile(r'\.pdf', re.I))
                if pdf_link:
                    href = pdf_link.get('href', '')
                    if not href.startswith('http'):
                        href = urljoin(self.XPLORE_BASE, href)
                    return href

        except Exception as e:
            logger.debug(f"获取stamp页面失败: {e}")

        return None

    def download_paper(self, paper_info, save_path, session=None, max_retries=5):
        """
        下载单篇论文（带重试机制）

        Args:
            paper_info: 论文信息字典
            save_path: 保存路径
            session: requests Session对象
            max_retries: 最大重试次数

        Returns:
            是否下载成功
        """
        if save_path.exists() and save_path.stat().st_size > 1000:
            return True

        if session is None:
            session = self.session

        # 获取article_number
        article_number = paper_info.get('article_number', '')

        # 构建多个可能的PDF URL
        pdf_urls = []

        # 1. 直接的ielx PDF URL（最直接的方式）
        if article_number:
            # IEEE的直接PDF链接格式
            pdf_urls.append(f"{self.XPLORE_BASE}/ielx7/{self.YEAR_PROCEEDING_IDS.get(2023, '')}/{article_number[:8]}/{article_number}.pdf")

        # 2. 原始的stamp URL
        pdf_url = paper_info.get('pdf_url', '')
        if pdf_url:
            pdf_urls.append(pdf_url)

        # 3. 尝试从stamp页面获取
        if article_number:
            stamp_pdf_url = self._get_pdf_url_from_stamp(article_number, session)
            if stamp_pdf_url:
                pdf_urls.insert(0, stamp_pdf_url)  # 优先使用

        if not pdf_urls:
            logger.warning(f"论文没有PDF URL: {paper_info.get('title', 'Unknown')[:50]}")
            return False

        pdf_url = pdf_urls[0] if pdf_urls else ''

        if not pdf_url:
            logger.warning(f"论文没有PDF URL: {paper_info.get('title', 'Unknown')[:50]}")
            return False

        # 重试循环
        for attempt in range(max_retries):
            temp_path = save_path.with_suffix('.tmp')

            try:
                if attempt > 0:
                    wait_time = min(2 ** (attempt - 1), 5)
                    logger.info(f"重试下载 (第{attempt + 1}/{max_retries}次): {paper_info.get('title', '')[:50]}...")
                    time.sleep(wait_time)

                # 设置更长的超时时间
                response = session.get(
                    pdf_url,
                    timeout=(10, 120),
                    stream=True,
                    allow_redirects=True
                )

                # 检查是否需要认证
                if response.status_code in [401, 403]:
                    logger.warning(f"需要认证才能下载（可能在付费墙内）: {paper_info.get('title', '')[:50]}")
                    return False

                response.raise_for_status()

                # 检查Content-Length
                content_length = response.headers.get('Content-Length')
                if content_length and int(content_length) < 10000:
                    logger.warning(f"文件太小 ({content_length} bytes)，可能不是完整PDF")

                # 保存完整文件，同时验证内容
                total_size = 0
                first_chunk = None

                with open(temp_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            if first_chunk is None:
                                first_chunk = chunk

                                # 检查是否是PDF
                                if chunk[:4] != b'%PDF':
                                    preview_str = chunk[:500].decode('utf-8', errors='ignore').lower()
                                    if '<html' in preview_str or '<!doctype' in preview_str:
                                        if 'login' in preview_str or 'sign in' in preview_str or 'access denied' in preview_str:
                                            logger.warning(f"需要登录才能下载: {paper_info.get('title', '')[:50]}")
                                            return False
                                        logger.warning(f"下载的不是PDF（收到HTML）: {paper_info.get('title', '')[:50]}")
                                        if attempt < max_retries - 1:
                                            break
                                        return False

                            f.write(chunk)
                            total_size += len(chunk)

                if not first_chunk:
                    logger.warning(f"下载内容为空: {paper_info.get('title', '')[:50]}")
                    if temp_path.exists():
                        temp_path.unlink()
                    if attempt < max_retries - 1:
                        continue
                    return False

                # 验证文件大小（PDF论文通常至少几十KB）
                file_size = temp_path.stat().st_size
                if file_size < 50000:  # 50KB 最小阈值
                    logger.warning(f"下载的文件过小 ({file_size} bytes): {save_path.name}")
                    temp_path.unlink()
                    if attempt < max_retries - 1:
                        continue
                    return False

                # 验证PDF格式
                with open(temp_path, 'rb') as f:
                    if f.read(4) != b'%PDF':
                        logger.error(f"保存的文件不是有效的PDF: {save_path.name}")
                        temp_path.unlink()
                        if attempt < max_retries - 1:
                            continue
                        return False

                # 原子性重命名
                temp_path.replace(save_path)
                return True

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError,
                    requests.exceptions.ChunkedEncodingError) as e:
                if attempt < max_retries - 1:
                    logger.warning(f"网络错误，将重试: {type(e).__name__}")
                    if temp_path.exists():
                        temp_path.unlink()
                    continue
                else:
                    logger.error(f"下载失败（已重试{max_retries}次）: {e}")
                    if temp_path.exists():
                        temp_path.unlink()
                    return False

            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response else 'Unknown'
                logger.error(f"HTTP错误 {status_code}: {paper_info.get('title', '')[:50]}")
                if temp_path.exists():
                    temp_path.unlink()
                return False

            except Exception as e:
                logger.error(f"下载失败: {e}")
                if temp_path.exists():
                    temp_path.unlink()
                if attempt < max_retries - 1:
                    continue
                return False

        return False

    def _download_worker(self, paper_info, save_path, index, total):
        """
        并发下载工作线程
        """
        session = requests.Session()
        session.headers.update(self.session.headers)

        title = paper_info.get('title', 'Unknown')
        filename = save_path.name

        if save_path.exists() and save_path.stat().st_size > 1000:
            with self.download_lock:
                self.downloaded_count += 1
            logger.info(f"[{index}/{total}] 跳过已存在: {filename[:60]}")
            return (True, paper_info, index)

        logger.info(f"[{index}/{total}] 下载: {title[:60]}...")

        success = self.download_paper(paper_info, save_path, session=session)

        with self.download_lock:
            if success:
                self.downloaded_count += 1
                logger.info(f"[{index}/{total}] ✓ 下载成功: {filename[:60]}")
            else:
                self.failed_count += 1
                logger.error(f"[{index}/{total}] ✗ 下载失败: {filename[:60]}")

        session.close()
        return (success, paper_info, index)

    def save_metadata(self, papers, year):
        """
        保存论文元数据
        """
        formats = ['txt', 'csv', 'json'] if self.metadata_format == 'all' else [self.metadata_format]
        base_path = self.base_dir / str(year)

        for fmt in formats:
            if fmt == 'txt':
                metadata_file = base_path / "metadata.txt"
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    f.write(f"IEEE S&P {year} Papers\n")
                    f.write(f"=" * 50 + "\n\n")
                    for paper in papers:
                        f.write(f"Title: {paper['title']}\n")
                        if paper.get('authors'):
                            f.write(f"Authors: {paper['authors']}\n")
                        if paper.get('pdf_url'):
                            f.write(f"PDF URL: {paper['pdf_url']}\n")
                        if paper.get('doi'):
                            f.write(f"DOI: {paper['doi']}\n")
                        f.write("\n")

            elif fmt == 'csv':
                metadata_file = base_path / "metadata.csv"
                with open(metadata_file, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Title', 'Authors', 'PDF URL', 'DOI', 'Article ID'])
                    for paper in papers:
                        writer.writerow([
                            paper.get('title', ''),
                            paper.get('authors', ''),
                            paper.get('pdf_url', ''),
                            paper.get('doi', ''),
                            paper.get('article_id', ''),
                        ])

            elif fmt == 'json':
                metadata_file = base_path / "metadata.json"
                metadata = {
                    'conference': 'IEEE S&P',
                    'year': year,
                    'total_papers': len(papers),
                    'papers': papers
                }
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)

        logger.info(f"元数据已保存为: {', '.join(formats)} 格式")

    def crawl_year(self, year):
        """
        爬取指定年份的所有论文

        Args:
            year: 会议年份

        Returns:
            下载的论文数量
        """
        logger.info(f"开始爬取 {year} 年 IEEE S&P 论文")

        # 检查开放获取状态
        current_year = 2024
        if year >= current_year:
            logger.warning(f"⚠️ {year} 年的论文可能还在付费墙内（会议结束后1年内需付费）")

        # 提取论文列表
        papers = self.extract_papers(year)

        if not papers:
            logger.warning(f"{year} 年未找到论文")
            return 0

        logger.info(f"找到 {len(papers)} 篇论文")

        # 过滤掉没有PDF URL的论文
        papers_with_url = [p for p in papers if p.get('pdf_url')]
        if len(papers_with_url) < len(papers):
            logger.warning(f"{len(papers) - len(papers_with_url)} 篇论文没有PDF URL")

        if not papers_with_url:
            logger.warning(f"{year} 年没有可下载的论文（无PDF URL）")
            # 仍然保存元数据
            save_dir = self.base_dir / str(year)
            save_dir.mkdir(parents=True, exist_ok=True)
            self.save_metadata(papers, year)
            return 0

        # 创建保存目录
        save_dir = self.base_dir / str(year) / "papers"
        save_dir.mkdir(parents=True, exist_ok=True)

        # 重置计数器
        self.downloaded_count = 0
        self.failed_count = 0

        # 准备下载任务
        download_tasks = []
        skipped = 0

        for i, paper in enumerate(papers_with_url, 1):
            title = paper.get('title', f'paper_{i}')
            safe_title = self.sanitize_filename(title)
            filename = f"{safe_title}.pdf"
            save_path = save_dir / filename

            if save_path.exists() and save_path.stat().st_size > 1000:
                skipped += 1
                continue

            download_tasks.append((paper, save_path, i, len(papers_with_url)))

        logger.info(f"需要下载: {len(download_tasks)} 篇, 已存在: {skipped} 篇, 总计: {len(papers_with_url)} 篇")

        # 并发下载
        if download_tasks:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_task = {
                    executor.submit(self._download_worker, paper, path, idx, total): (paper, path, idx)
                    for paper, path, idx, total in download_tasks
                }

                for future in as_completed(future_to_task):
                    try:
                        future.result()
                    except Exception as e:
                        logger.error(f"下载任务异常: {e}")

            # 添加延迟避免请求过快
            time.sleep(self.delay)

        downloaded = self.downloaded_count + skipped
        failed = self.failed_count

        # 保存元数据（包括所有论文，不只是有URL的）
        self.save_metadata(papers, year)

        logger.info(f"{year} 年完成: 成功 {downloaded}, 失败 {failed}, 总计 {len(papers)}")
        return downloaded

    def crawl(self, years=None):
        """
        爬取指定年份的论文

        Args:
            years: 年份列表，如果为None则爬取最近5年（开放获取的）
        """
        if years is None:
            # 默认爬取2020-2023年（应该都是开放获取的）
            # 2024年可能还在付费墙内
            years = [2023, 2022, 2021, 2020]

        logger.info(f"开始爬取 IEEE S&P 论文，年份: {years}")
        logger.info("=" * 60)
        logger.info("开放获取说明:")
        logger.info("- 2023年及更早: 应该免费开放获取")
        logger.info("- 2024年: 可能在付费墙内（2025年5月后开放）")
        logger.info("=" * 60)

        total_downloaded = 0
        for year in years:
            try:
                time.sleep(self.delay)
                count = self.crawl_year(year)
                total_downloaded += count
            except Exception as e:
                logger.error(f"爬取 {year} 年失败: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                continue

        logger.info(f"全部完成！共下载 {total_downloaded} 篇论文")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description='IEEE S&P 论文爬虫 (基于CSDL开放获取)',
        epilog='''
示例:
  # 下载2023年和2022年的论文
  uv run python crawler_ieee_sp.py -y 2023 2022

  # 下载最近5年的论文（默认）
  uv run python crawler_ieee_sp.py

注意: 2024年的论文可能还在付费墙内，需等到2025年5月后才能免费下载
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('-y', '--years', nargs='+', type=int,
                       help='要下载的年份列表，例如: -y 2023 2022 2021')
    parser.add_argument('-d', '--dir', default='IEEE_SP',
                       help='保存目录（默认: IEEE_SP）')
    parser.add_argument('--delay', type=float, default=1.0,
                       help='请求之间的延迟秒数（默认: 1.0）')
    parser.add_argument('--workers', type=int, default=5,
                       help='并发下载的最大线程数（默认: 5）')
    parser.add_argument('--format', choices=['txt', 'csv', 'json', 'all'], default='csv',
                       help='元数据保存格式（默认: csv）')

    args = parser.parse_args()

    crawler = IEEESPCrawler(
        base_dir=args.dir,
        delay=args.delay,
        max_workers=args.workers,
        metadata_format=args.format
    )
    crawler.crawl(years=args.years)


if __name__ == '__main__':
    main()
