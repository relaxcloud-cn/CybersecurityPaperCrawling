#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IEEE S&P (IEEE Symposium on Security and Privacy) 论文爬虫
需要IEEE会员账号登录

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
import getpass

# 配置日志
# 确保logs目录存在
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
    """IEEE S&P会议论文爬虫"""
    
    BASE_URL = "https://ieeexplore.ieee.org"
    LOGIN_URL = "https://ieeexplore.ieee.org/Xplore/login.jsp"
    
    def __init__(self, base_dir="IEEE_SP", delay=1.0, max_workers=5, metadata_format='csv', 
                 username=None, password=None):
        """
        初始化爬虫
        
        Args:
            base_dir: 保存论文的基础目录
            delay: 请求之间的延迟（秒），避免对服务器造成压力
            max_workers: 并发下载的最大线程数
            metadata_format: 元数据保存格式，可选: 'txt', 'csv', 'json', 'all'
            username: IEEE用户名（可从环境变量获取）
            password: IEEE密码（可从环境变量获取）
        """
        self.base_dir = Path(base_dir)
        self.delay = delay
        self.max_workers = max_workers
        self.metadata_format = metadata_format
        
        # 获取用户名和密码
        self.username = username or os.getenv('IEEE_USERNAME')
        self.password = password or os.getenv('IEEE_PASSWORD')
        
        if not self.username or not self.password:
            logger.error("未提供IEEE用户名或密码！")
            logger.error("请设置环境变量 IEEE_USERNAME 和 IEEE_PASSWORD")
            logger.error("或通过命令行参数 --username 和 --password 提供")
            raise ValueError("需要提供IEEE用户名和密码")
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        # 如果设置了代理，使用代理
        http_proxy = os.getenv('HTTP_PROXY') or os.getenv('http_proxy')
        https_proxy = os.getenv('HTTPS_PROXY') or os.getenv('https_proxy')
        if http_proxy or https_proxy:
            proxies = {}
            if http_proxy:
                proxies['http'] = http_proxy
            if https_proxy:
                proxies['https'] = https_proxy
            self.session.proxies.update(proxies)
            logger.info(f"使用代理: {proxies}")
        
        self.download_lock = Lock()
        self.downloaded_count = 0
        self.failed_count = 0
        
        # 登录（允许失败后继续，因为可能网络问题）
        login_success = self.login()
        if not login_success:
            logger.warning("登录可能失败，但将继续尝试（可能是网络问题）")
            # 不直接抛出异常，让后续代码尝试
    
    def login(self):
        """
        登录IEEE Xplore
        
        Returns:
            是否登录成功
        """
        logger.info("正在登录IEEE Xplore...")
        
        try:
            # 方法1: 先访问主页获取初始cookie
            logger.info("访问IEEE Xplore主页...")
            try:
                main_response = self.session.get(self.BASE_URL, timeout=60)
                logger.info(f"主页访问成功: {main_response.status_code}")
            except requests.exceptions.Timeout:
                logger.warning("主页访问超时，可能是网络问题")
                return False
            except Exception as e:
                logger.warning(f"主页访问失败: {e}")
                return False
            
            # 方法2: 尝试直接访问登录页面
            logger.info("访问登录页面...")
            response = self.session.get(self.LOGIN_URL, timeout=60)
            if response.status_code != 200:
                logger.warning(f"无法访问登录页面: {response.status_code}")
                return False
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找登录表单
            form = soup.find('form', {'id': 'loginForm'}) or soup.find('form', {'method': 'POST'})
            
            if form:
                action = form.get('action', '')
                if action and not action.startswith('http'):
                    action = urljoin(self.BASE_URL, action)
                
                # 准备登录数据
                login_data = {
                    'username': self.username,
                    'password': self.password,
                }
                
                # 查找表单中的隐藏字段
                hidden_inputs = form.find_all('input', type='hidden')
                for hidden in hidden_inputs:
                    name = hidden.get('name')
                    value = hidden.get('value', '')
                    if name:
                        login_data[name] = value
                
                # 提交登录
                login_url = action if action else self.LOGIN_URL
                logger.info(f"提交登录表单到: {login_url}")
                logger.debug(f"登录数据字段: {list(login_data.keys())}")
                
                response = self.session.post(login_url, data=login_data, timeout=30, allow_redirects=True)
                
                # 检查是否登录成功
                if 'login' not in response.url.lower() or 'sign in' not in response.text.lower():
                    # 检查是否包含用户名或会员信息
                    if self.username.split('@')[0].lower() in response.text.lower() or 'sign out' in response.text.lower():
                        logger.info("✓ 登录成功")
                        return True
                
                # 检查错误信息
                if 'error' in response.text.lower() or 'invalid' in response.text.lower():
                    logger.error("登录失败：用户名或密码错误")
                    return False
                
                logger.warning("登录状态不明确，尝试继续...")
                return True
            
            # 方法2: 尝试查找其他登录方式
            logger.info("未找到标准登录表单，尝试查找其他登录方式...")
            
            # 查找可能的登录按钮或链接
            login_buttons = soup.find_all(['button', 'a'], string=re.compile(r'sign in|login', re.I))
            if login_buttons:
                logger.info(f"找到 {len(login_buttons)} 个登录按钮/链接")
                for btn in login_buttons:
                    href = btn.get('href', '')
                    onclick = btn.get('onclick', '')
                    logger.debug(f"登录元素: href={href}, onclick={onclick[:100]}")
            
            # 尝试使用SAML或OAuth认证
            # IEEE Xplore可能使用统一的IEEE账户系统
            saml_url = "https://ieeexplore.ieee.org/rest/account/login"
            
            logger.info("尝试使用REST API登录...")
            login_payload = {
                'username': self.username,
                'password': self.password,
            }
            
            api_response = self.session.post(saml_url, json=login_payload, timeout=30)
            logger.info(f"API登录响应状态: {api_response.status_code}")
            
            if api_response.status_code == 200:
                try:
                    result = api_response.json()
                    if result.get('success') or 'token' in result:
                        logger.info("✓ REST API登录成功")
                        return True
                except:
                    pass
            
            # 如果以上都失败，尝试直接访问主页面检查登录状态
            try:
                main_response = self.session.get(self.BASE_URL, timeout=60)
                if 'sign out' in main_response.text.lower() or 'logout' in main_response.text.lower():
                    logger.info("✓ 可能已登录（检测到登出链接）")
                    return True
            except:
                pass
            
            logger.warning("无法确定登录状态，将尝试继续执行（可能需要手动验证）...")
            return True
            
        except Exception as e:
            logger.error(f"登录过程出错: {e}")
            return False
    
    def search_papers(self, year):
        """
        搜索指定年份的IEEE S&P论文
        
        Args:
            year: 会议年份
            
        Returns:
            论文信息列表
        """
        logger.info(f"搜索 {year} 年 IEEE S&P 论文...")
        
        papers = []
        
        try:
            # 使用IEEE Xplore REST API
            api_url = f"{self.BASE_URL}/rest/search"
            search_query = f'"IEEE Symposium on Security and Privacy" AND {year}'
            
            payload = {
                "queryText": search_query,
                "highlight": True,
                "returnType": "SEARCH",
                "matchPubs": True,
                "rowsPerPage": 100,
                "pageNumber": 1,
                "returnFacets": ["ALL"]
            }
            
            # 设置正确的请求头
            headers = {
                'Accept': 'application/json, text/plain, */*',
                'Content-Type': 'application/json',
                'Origin': 'https://ieeexplore.ieee.org',
                'Referer': 'https://ieeexplore.ieee.org/search/searchresult.jsp',
            }
            
            logger.info(f"使用REST API搜索: {api_url}")
            logger.info(f"搜索查询: {search_query}")
            
            response = self.session.post(api_url, json=payload, headers=headers, timeout=60)
            if response.status_code != 200:
                logger.warning(f"API搜索失败: {response.status_code}")
                return []
            
            # 解析JSON响应
            try:
                data = response.json()
            except json.JSONDecodeError:
                logger.error("API响应不是JSON格式")
                return []
            
            total_records = data.get('totalRecords', 0)
            records = data.get('records', [])
            total_pages = data.get('totalPages', 1)
            
            logger.info(f"找到 {total_records} 条记录，共 {total_pages} 页")
            logger.info(f"当前页: {len(records)} 条记录")
            
            # 处理当前页的记录
            for record in records:
                title = record.get('articleTitle', '')
                if not title:
                    continue
                
                # 获取文档链接
                doc_link = record.get('documentLink', '')
                if not doc_link.startswith('http'):
                    doc_link = urljoin(self.BASE_URL, doc_link)
                
                # 构造PDF URL
                # 优先使用API返回的pdfLink字段
                pdf_link = record.get('pdfLink', '')
                if pdf_link:
                    # pdfLink格式通常是: /stamp/stamp.jsp?tp=&arnumber={articleNumber}
                    # 需要访问这个URL获取实际PDF，或者直接使用article.pdf格式
                    article_number = record.get('articleNumber', '')
                    if article_number:
                        pdf_url = f"{self.BASE_URL}/document/{article_number}/article.pdf"
                    else:
                        # 从pdfLink中提取arnumber
                        ar_match = re.search(r'arnumber=(\d+)', pdf_link)
                        if ar_match:
                            pdf_url = f"{self.BASE_URL}/document/{ar_match.group(1)}/article.pdf"
                        else:
                            pdf_url = None
                else:
                    # 如果没有pdfLink，使用articleNumber构造
                    article_number = record.get('articleNumber', '')
                    if article_number:
                        pdf_url = f"{self.BASE_URL}/document/{article_number}/article.pdf"
                    else:
                        # 从documentLink提取
                        doc_match = re.search(r'/document/(\d+)', doc_link)
                        if doc_match:
                            pdf_url = f"{self.BASE_URL}/document/{doc_match.group(1)}/article.pdf"
                        else:
                            pdf_url = None
                
                if not pdf_url:
                    logger.warning(f"无法构造PDF URL: {title}")
                    continue
                
                # 提取作者
                authors = []
                for author in record.get('authors', []):
                    author_name = author.get('preferredName', '') or author.get('normalizedName', '')
                    if author_name:
                        authors.append(author_name)
                authors_str = ', '.join(authors)
                
                papers.append({
                    'title': title,
                    'pdf_url': pdf_url,
                    'authors': authors_str,
                    'session': '',
                    'doi': record.get('doi', ''),
                    'document_link': doc_link,
                })
            
            # 如果有多页，获取所有页
            if total_pages > 1:
                logger.info(f"需要获取 {total_pages} 页数据")
                for page in range(2, total_pages + 1):
                    logger.info(f"获取第 {page}/{total_pages} 页...")
                    payload['pageNumber'] = page
                    
                    time.sleep(self.delay)  # 添加延迟避免请求过快
                    response = self.session.post(api_url, json=payload, headers=headers, timeout=60)
                    
                    if response.status_code == 200:
                        try:
                            page_data = response.json()
                            page_records = page_data.get('records', [])
                            
                            for record in page_records:
                                title = record.get('articleTitle', '')
                                if not title:
                                    continue
                                
                                doc_link = record.get('documentLink', '')
                                if not doc_link.startswith('http'):
                                    doc_link = urljoin(self.BASE_URL, doc_link)
                                
                                # 使用相同的PDF URL构造逻辑
                                pdf_link = record.get('pdfLink', '')
                                if pdf_link:
                                    article_number = record.get('articleNumber', '')
                                    if article_number:
                                        pdf_url = f"{self.BASE_URL}/document/{article_number}/article.pdf"
                                    else:
                                        ar_match = re.search(r'arnumber=(\d+)', pdf_link)
                                        if ar_match:
                                            pdf_url = f"{self.BASE_URL}/document/{ar_match.group(1)}/article.pdf"
                                        else:
                                            continue
                                else:
                                    article_number = record.get('articleNumber', '')
                                    if article_number:
                                        pdf_url = f"{self.BASE_URL}/document/{article_number}/article.pdf"
                                    else:
                                        doc_match = re.search(r'/document/(\d+)', doc_link)
                                        if doc_match:
                                            pdf_url = f"{self.BASE_URL}/document/{doc_match.group(1)}/article.pdf"
                                        else:
                                            continue
                                
                                authors = []
                                for author in record.get('authors', []):
                                    author_name = author.get('preferredName', '') or author.get('normalizedName', '')
                                    if author_name:
                                        authors.append(author_name)
                                authors_str = ', '.join(authors)
                                
                                papers.append({
                                    'title': title,
                                    'pdf_url': pdf_url,
                                    'authors': authors_str,
                                    'session': '',
                                    'doi': record.get('doi', ''),
                                    'document_link': doc_link,
                                })
                        except json.JSONDecodeError:
                            logger.warning(f"第 {page} 页响应解析失败")
                            continue
            
            logger.info(f"提取到 {len(papers)} 篇论文")
            return papers
            
        except Exception as e:
            logger.error(f"搜索论文失败: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return []
    
    def sanitize_filename(self, filename):
        """清理文件名"""
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        filename = re.sub(r'\s+', ' ', filename).strip()
        if len(filename) > 200:
            filename = filename[:200]
        return filename
    
    def save_metadata(self, papers, year):
        """保存论文元数据"""
        formats = []
        if self.metadata_format == 'all':
            formats = ['txt', 'csv', 'json']
        else:
            formats = [self.metadata_format]
        
        base_path = self.base_dir / str(year)
        
        for fmt in formats:
            if fmt == 'txt':
                metadata_file = base_path / "metadata.txt"
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    f.write(f"IEEE S&P {year} Papers\n")
                    f.write(f"=" * 50 + "\n\n")
                    for paper in papers:
                        f.write(f"Title: {paper['title']}\n")
                        f.write(f"PDF URL: {paper['pdf_url']}\n")
                        if paper.get('doi'):
                            f.write(f"DOI: {paper['doi']}\n")
                        if paper.get('authors'):
                            f.write(f"Authors: {paper['authors']}\n")
                        f.write("\n")
            
            elif fmt == 'csv':
                metadata_file = base_path / "metadata.csv"
                with open(metadata_file, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Title', 'Authors', 'PDF URL', 'DOI', 'Session'])
                    for paper in papers:
                        writer.writerow([
                            paper['title'],
                            paper.get('authors', ''),
                            paper['pdf_url'],
                            paper.get('doi', ''),
                            paper.get('session', '')
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
    
    def download_paper(self, paper_info, save_path, session=None):
        """下载单篇论文"""
        if save_path.exists():
            return True
        
        try:
            if session is None:
                session = self.session
            
            response = session.get(paper_info['pdf_url'], timeout=30, stream=True)
            response.raise_for_status()
            
            # 检查是否为PDF
            content_type = response.headers.get('Content-Type', '')
            if 'pdf' not in content_type.lower():
                content = response.content[:4]
                if content != b'%PDF':
                    logger.warning(f"文件可能不是PDF: {paper_info['pdf_url']}")
            
            # 保存文件
            temp_path = save_path.with_suffix('.tmp')
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # 验证文件大小
            if temp_path.stat().st_size < 1000:
                logger.warning(f"下载的文件过小: {save_path}")
                temp_path.unlink()
                return False
            
            temp_path.replace(save_path)
            return True
            
        except Exception as e:
            logger.error(f"下载论文失败: {e}")
            if 'temp_path' in locals() and temp_path.exists():
                temp_path.unlink()
            return False
    
    def _download_worker(self, paper_info, save_path, index, total):
        """并发下载工作线程"""
        session = requests.Session()
        session.headers.update(self.session.headers)
        # 复制cookies
        session.cookies.update(self.session.cookies)
        
        title = paper_info['title']
        filename = save_path.name
        
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
        """爬取指定年份的所有论文"""
        logger.info(f"开始爬取 {year} 年 IEEE S&P 论文")
        
        # 搜索论文
        papers = self.search_papers(year)
        if not papers:
            logger.warning(f"{year} 年未找到论文")
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
        
        for i, paper in enumerate(papers, 1):
            title = paper['title']
            safe_title = self.sanitize_filename(title)
            filename = f"{safe_title}.pdf"
            save_path = save_dir / filename
            
            if save_path.exists() and save_path.stat().st_size > 1000:
                skipped += 1
                continue
            
            download_tasks.append((paper, save_path, i, len(papers)))
        
        logger.info(f"需要下载: {len(download_tasks)} 篇, 已存在: {skipped} 篇, 总计: {len(papers)} 篇")
        
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
        
        downloaded = self.downloaded_count + skipped
        failed = self.failed_count
        
        # 保存元数据
        self.save_metadata(papers, year)
        
        logger.info(f"{year} 年完成: 成功 {downloaded}, 失败 {failed}, 总计 {len(papers)}")
        return downloaded
    
    def crawl(self, years=None):
        """爬取指定年份的论文"""
        if years is None:
            years = list(range(2020, 2025))
        
        logger.info(f"开始爬取 IEEE S&P 论文，年份: {years}")
        
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
    
    parser = argparse.ArgumentParser(description='IEEE S&P 论文爬虫')
    parser.add_argument('-y', '--years', nargs='+', type=int, 
                       help='要下载的年份列表，例如: -y 2023 2024')
    parser.add_argument('-d', '--dir', default='IEEE_SP',
                       help='保存目录（默认: IEEE_SP）')
    parser.add_argument('--delay', type=float, default=1.0,
                       help='请求之间的延迟秒数（默认: 1.0，并发下载时此参数影响较小）')
    parser.add_argument('--workers', type=int, default=5,
                       help='并发下载的最大线程数（默认: 5）')
    parser.add_argument('--format', choices=['txt', 'csv', 'json', 'all'], default='csv',
                       help='元数据保存格式（默认: csv，可选: txt, csv, json, all）')
    parser.add_argument('--username', type=str, default=None,
                       help='IEEE用户名（也可通过环境变量IEEE_USERNAME提供）')
    parser.add_argument('--password', type=str, default=None,
                       help='IEEE密码（也可通过环境变量IEEE_PASSWORD提供）')
    
    args = parser.parse_args()
    
    # 如果没有提供密码，尝试从环境变量获取
    password = args.password or os.getenv('IEEE_PASSWORD')
    username = args.username or os.getenv('IEEE_USERNAME')
    
    # 如果还是没有，提示输入
    if not username:
        username = input("请输入IEEE用户名: ").strip()
    if not password:
        password = getpass.getpass("请输入IEEE密码: ")
    
    crawler = IEEESPCrawler(
        base_dir=args.dir,
        delay=args.delay,
        max_workers=args.workers,
        metadata_format=args.format,
        username=username,
        password=password
    )
    crawler.crawl(years=args.years)


if __name__ == '__main__':
    main()
