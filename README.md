# 网络安全顶会论文爬虫

自动下载网络安全四大顶会论文，并支持 PDF 转 Markdown 功能。

## 支持的会议

| 会议 | 下载状态 | 说明 |
|------|----------|------|
| **USENIX Security** | ✅ 免费下载 | 完全开放获取 |
| **NDSS** | ✅ 免费下载 | 完全开放获取 |
| **IEEE S&P** | ✅ 免费下载 | 1年后开放获取（2023及更早可下载） |
| **ACM CCS** | ✅ 支持下载 | 需要 FlareSolverr 绕过 Cloudflare |

## 快速开始

### 安装

```bash
# 安装 uv（如果还没有安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 克隆项目
git clone https://github.com/your-username/CybersecurityPaperCrawling.git
cd CybersecurityPaperCrawling/cybersec_papers

# 安装依赖（uv 会自动管理）
uv sync
```

### 下载论文

```bash
cd cybersec_papers

# USENIX Security
uv run python -m cybersec_papers crawl usenix -y 2023 2024

# NDSS
uv run python -m cybersec_papers crawl ndss -y 2023 2024

# IEEE S&P（2023及更早免费）
uv run python -m cybersec_papers crawl ieee_sp -y 2023 2022 2021

# ACM CCS（需要先启动 FlareSolverr）
docker run -d -p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest
uv run python -m cybersec_papers crawl acm_ccs -y 2023 2022 2021
```

### PDF 转 Markdown

使用 [MinerU](https://github.com/opendatalab/MinerU) 将 PDF 转换为 Markdown，支持 GPU 加速。

```bash
# 查看转换进度
uv run python convert_pdf.py --status

# 运行转换（默认 6 个并行 worker）
uv run python convert_pdf.py

# 自定义 worker 数量
uv run python convert_pdf.py --workers 8
```

## 项目结构

```
CybersecurityPaperCrawling/
├── cybersec_papers/           # 主程序包
│   ├── src/cybersec_papers/   # 源代码
│   │   ├── crawlers/          # 各会议爬虫
│   │   ├── converter/         # PDF 转 Markdown
│   │   ├── services/          # 外部服务（FlareSolverr 等）
│   │   └── core/              # 基础类和工具
│   ├── convert_pdf.py         # PDF 转 Markdown 脚本
│   └── pyproject.toml
├── {CONFERENCE}/YYYY/         # 下载的论文（不在 git 中）
│   ├── papers/*.pdf
│   ├── markdown/*/            # 转换后的 Markdown
│   └── metadata.csv
└── logs/                      # 日志文件（不在 git 中）
```

## 常用参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-y, --years` | 下载年份 | 2020-2024 |
| `--workers` | 并发数 | 5（爬虫）/ 6（转换）|
| `--delay` | 请求延迟（秒）| 1.0 |

## 开放获取说明

### IEEE S&P
- 论文发表后 1 年内需付费
- 1 年后开放获取（2023 及更早可免费下载）

### ACM CCS
- ACM 数字图书馆将于 2026 年 1 月完全开放获取
- 目前需要 FlareSolverr 绕过 Cloudflare 保护
- 支持 arXiv 和 Semantic Scholar 作为备用来源

## 依赖

- Python >= 3.10
- [uv](https://github.com/astral-sh/uv) - Python 包管理器
- [MinerU](https://github.com/opendatalab/MinerU) - PDF 转 Markdown（可选，需要 GPU）
- [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) - 绕过 Cloudflare（ACM CCS 需要）

## 注意事项

1. **遵守版权**：下载的论文仅用于个人研究
2. **合理使用**：设置适当延迟，避免对服务器造成压力
3. **存储空间**：完整下载需要约 50GB 空间

## 许可证

本项目仅供学习和研究使用。请遵守相关会议和论文的版权规定。
