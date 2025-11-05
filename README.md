# 网络安全顶会论文爬虫

本项目包含用于下载网络安全四大顶会论文的Python爬虫脚本。

## 支持的会议

- ✅ **USENIX Security** - 完全支持，免费下载
- ✅ **NDSS** - 完全支持，免费下载
- 🔐 **IEEE S&P** - 需要会员认证（需要提供用户名密码，详见下方说明）
- 🔐 **ACM CCS** - 需要会员认证（需要提供用户名密码，详见下方说明）

**说明**：
- **IEEE S&P和ACM CCS**：如果您有IEEE或ACM会员资格，可以提供用户名和密码，我们可以实现自动下载功能。详见 `IEEE_ACM_Implementation_Guide.md`
- **免费用户**：如果没有会员资格，建议通过机构订阅、DBLP或作者个人主页获取论文


## 四大顶会论文下载情况

### USENIX Security Symposium
- **官方网站**: https://www.usenix.org/conference/usenixsecurity
- **下载情况**: ✅ 可以免费下载PDF
- **特点**: 支持多种格式下载（PDF、EPUB、MOBI），最友好的会议

### NDSS (Network and Distributed System Security Symposium)
- **官方网站**: https://www.ndss-symposium.org
- **下载情况**: ✅ 可以免费下载PDF
- **特点**: 论文通常在会议结束后公开

### IEEE S&P (IEEE Symposium on Security and Privacy)
- **官方网站**: http://www.ieee-security.org/TC/SP-Index.html
- **下载情况**: ✅ **已实现，需要IEEE会员账号**
- **访问方式**:
  1. **IEEE Xplore**: 需要机构订阅或个人会员资格（https://ieeexplore.ieee.org）
  2. **DBLP数据库**: 可查看论文列表和元数据（https://dblp.uni-trier.de/db/conf/sp/）
  3. **作者个人主页**: 部分作者会提供免费版本
  4. **arXiv预印本**: 部分论文可能有预印本版本
  5. **机构访问**: 如果机构订阅了IEEE Xplore，可通过机构网络访问
- **网络要求**: 如果网络环境无法直接访问IEEE Xplore，可能需要配置代理（详见下方网络配置说明）

### ACM CCS (ACM Conference on Computer and Communications Security)
- **官方网站**: http://www.sigsac.org/ccs.html
- **下载情况**: ❌ **无法直接免费下载**
- **访问方式**:
  1. **ACM Digital Library**: 需要机构订阅或个人会员资格（https://dl.acm.org）
  2. **DBLP数据库**: 可查看论文列表和元数据（https://dblp.uni-trier.de/db/conf/ccs/）
  3. **作者个人主页**: 部分作者会提供免费版本
  4. **arXiv预印本**: 部分论文可能有预印本版本
  5. **机构访问**: 如果机构订阅了ACM Digital Library，可通过机构网络访问

## 目录结构

下载后的论文按照以下结构组织：

```
CybersecurityPaperCrawling/
├── crawler_usenix_security.py    # USENIX Security 爬虫脚本
├── crawler_ndss.py               # NDSS 爬虫脚本
├── crawler_ieee_sp.py            # IEEE S&P 爬虫脚本
├── logs/                         # 日志文件目录
│   ├── usenix_download.log
│   ├── ndss_download.log
│   └── ieee_sp_download.log
├── USENIX_Security/              # USENIX Security 论文目录
│   └── YYYY/
│       ├── papers/
│       │   ├── paper_title_1.pdf
│       │   └── ...
│       └── metadata.csv
├── NDSS/                         # NDSS 论文目录
│   └── YYYY/
│       ├── papers/
│       │   ├── paper_title_1.pdf
│       │   └── ...
│       └── metadata.csv
└── IEEE_SP/                      # IEEE S&P 论文目录
    └── YYYY/
        ├── papers/
        │   ├── paper_title_1.pdf
        │   └── ...
        └── metadata.csv
```

每个会议的论文按年份组织，包含：
- `papers/` 目录：存放所有PDF论文文件
- `metadata.csv`：论文元数据（标题、作者、链接等）

## 环境要求

- Python >= 3.8
- uv (Python包管理器)

## 安装

本项目使用 `uv` 管理Python环境和依赖：

```bash
# 安装uv（如果还没有安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 克隆项目后，uv会自动管理依赖
# 无需手动安装，使用 uv run python <script> 即可运行
```

**注意**：使用 `uv run python <script>` 而不是 `uv run <script>`，因为项目是脚本而非包。

## 使用方法

### 使用 uv run 运行

本项目使用 `uv` 管理Python环境，推荐使用 `uv run python` 运行脚本：

```bash
# USENIX Security 爬虫
uv run python crawler_usenix_security.py -y 2023 2024

# NDSS 爬虫
uv run python crawler_ndss.py -y 2023 2024

# IEEE S&P 爬虫（需要会员账号）
uv run python crawler_ieee_sp.py -y 2023 2024
```

### 通用参数

所有爬虫脚本都支持以下通用参数：

- `-y, --years`: 要下载的年份列表，例如 `-y 2021 2022 2023 2024 2025`
- `-d, --dir`: 保存目录（默认分别为: `USENIX_Security`, `NDSS`, `IEEE_SP`）
- `--delay`: 请求之间的延迟秒数（默认: 1.0秒，并发下载时此参数影响较小）
- `--workers`: 并发下载的最大线程数（默认: 5，可根据网络情况调整）
- `--format`: 元数据保存格式（默认: `csv`，可选: `txt`, `csv`, `json`, `all`）

### USENIX Security 论文爬虫

```bash
# 下载指定年份的论文
uv run python crawler_usenix_security.py -y 2021 2022 2023 2024 2025

# 下载所有可用年份的论文（不推荐，会下载很多）
uv run python crawler_usenix_security.py

# 指定保存目录
uv run python crawler_usenix_security.py -y 2024 -d MyPapers

# 设置并发线程数（默认5个线程）
uv run python crawler_usenix_security.py -y 2024 --workers 10

# 设置元数据格式（csv/txt/json/all，默认csv）
uv run python crawler_usenix_security.py -y 2024 --format csv

# 设置请求延迟（秒，并发下载时影响较小）
uv run python crawler_usenix_security.py -y 2024 --delay 2.0
```

### NDSS 论文爬虫

```bash
# 下载指定年份的论文
uv run python crawler_ndss.py -y 2021 2022 2023 2024 2025

# 下载所有可用年份的论文（不推荐，会下载很多）
uv run python crawler_ndss.py

# 指定保存目录
uv run python crawler_ndss.py -y 2024 -d MyPapers

# 设置并发线程数（默认5个线程，可提高下载速度）
uv run python crawler_ndss.py -y 2024 --workers 10

# 设置元数据格式（csv/txt/json/all，默认csv）
uv run python crawler_ndss.py -y 2024 --format csv

# 设置请求延迟（秒，并发下载时影响较小）
uv run python crawler_ndss.py -y 2024 --delay 2.0
```

### IEEE S&P 论文爬虫

**重要提示**：IEEE S&P 需要 IEEE 会员账号才能下载。您可以通过以下两种方式提供账号信息：

**方式1：环境变量（推荐）**
```bash
# 设置环境变量
export IEEE_USERNAME="your_username"
export IEEE_PASSWORD="your_password"

# 运行爬虫
uv run python crawler_ieee_sp.py -y 2021 2022 2023 2024 2025
```

**方式2：命令行参数**
```bash
# 下载指定年份的论文（会提示输入用户名和密码）
uv run python crawler_ieee_sp.py -y 2021 2022 2023 2024 2025

# 或直接提供用户名和密码（不推荐，密码会出现在命令行历史中）
uv run python crawler_ieee_sp.py -y 2024 --username your_username --password your_password
```

**其他参数示例：**
```bash
# 指定保存目录
uv run python crawler_ieee_sp.py -y 2024 -d MyPapers

# 设置并发线程数（默认5个线程）
uv run python crawler_ieee_sp.py -y 2024 --workers 10

# 设置元数据格式（csv/txt/json/all，默认csv）
uv run python crawler_ieee_sp.py -y 2024 --format csv

# 设置请求延迟（秒）
uv run python crawler_ieee_sp.py -y 2024 --delay 2.0
```

**网络配置（如果需要代理）：**
```bash
# 如果网络环境需要通过代理访问IEEE Xplore，可以设置代理环境变量
export HTTP_PROXY="http://proxy.example.com:8080"
export HTTPS_PROXY="http://proxy.example.com:8080"

# 然后运行爬虫
uv run python crawler_ieee_sp.py -y 2024
```

**安全提示：**
- 推荐使用环境变量方式提供账号信息，避免密码出现在命令行历史中
- 不要在代码或配置文件中硬编码密码
- 遵守IEEE使用条款，仅用于个人研究

## 功能特性

1. **并发下载**：使用多线程并发下载，大幅提高下载速度（默认5个线程）
2. **智能去重**：下载前自动检查文件是否存在，避免重复下载
3. **自动识别论文链接**：支持多种页面结构，自动识别PDF下载链接
4. **错误处理**：完善的错误处理和日志记录
5. **元数据保存**：支持多种格式保存论文元数据（TXT、CSV、JSON）
   - CSV格式：标准表格格式，便于Excel等工具打开
   - JSON格式：结构化数据，便于程序处理
   - TXT格式：人类可读格式（向后兼容）
6. **文件命名**：自动清理文件名，移除非法字符
7. **进度显示**：实时显示下载进度和统计信息
8. **日志记录**：详细的日志文件保存在 `logs/` 目录（`usenix_download.log`、`ndss_download.log`、`ieee_sp_download.log`）
9. **线程安全**：使用锁机制确保并发下载时的数据一致性

## 技术实现说明

### NDSS 爬虫修复

初始版本只下载了每年2-3篇论文，已修复：

1. **访问论文详情页**：从accepted-papers页面提取所有指向 `/ndss-paper/xxx/` 的链接，访问每个详情页获取PDF链接和标题
2. **改进标题提取**：优先从详情页的 `<h1>`, `<h2>`, `<h3>` 标签获取标题
3. **PDF链接识别**：在详情页查找所有PDF链接，优先选择包含"paper"的PDF，跳过"slides"PDF

修复后效果：NDSS 2024年从2篇增加到142篇论文

## 注意事项

1. **遵守版权**：请确保下载和使用论文符合相关版权规定，下载的论文仅用于个人研究，不要重新分发
2. **合理使用**：建议设置适当的延迟（`--delay`），避免对服务器造成压力，遵守平台使用条款
3. **网络连接**：确保网络连接稳定，某些论文可能较大，需要较长时间下载
4. **存储空间**：注意检查磁盘空间，历年论文可能占用大量存储空间
5. **账号安全**：
   - IEEE S&P需要IEEE会员账号，推荐使用环境变量方式提供账号信息
   - 不要在代码、配置文件或命令行历史中暴露密码
   - 遵守IEEE/ACM平台的使用条款，不要过度频繁请求
6. **网络配置**：如果网络环境无法直接访问IEEE Xplore，可能需要配置HTTP/HTTPS代理

## 示例输出

```
2024-01-01 10:00:00 - INFO - 开始爬取 2024 年 USENIX Security 论文
2024-01-01 10:00:01 - INFO - 找到2024年会议页面: https://www.usenix.org/conference/usenixsecurity24/technical-sessions
2024-01-01 10:00:02 - INFO - 从 https://... 提取到 85 篇论文
2024-01-01 10:00:03 - INFO - [1/85] 下载: Understanding and Detecting...
2024-01-01 10:00:05 - INFO - ✓ 下载成功: Understanding_and_Detecting.pdf
...
2024-01-01 10:30:00 - INFO - 2024 年完成: 成功 85, 失败 0, 总计 85
```

## 故障排除

### 问题1: 无法找到论文

**可能原因：**
- 网站结构发生变化
- 指定年份的会议尚未发布论文
- URL格式发生变化

**解决方案：**
- 检查日志文件查看详细错误信息
- 手动访问会议网站确认论文是否已发布
- 可能需要更新爬虫代码以适应新的页面结构

### 问题2: 下载失败

**可能原因：**
- 网络连接问题
- 服务器拒绝请求
- PDF链接失效

**解决方案：**
- 检查网络连接
- 增加延迟时间（`--delay`）
- 查看日志文件了解具体错误

### 问题3: 文件名包含特殊字符

**解决方案：**
脚本会自动清理文件名，移除非法字符。如果仍有问题，可以手动修改 `sanitize_filename` 方法。

## 开发计划

- [x] 实现并发下载支持（已完成）
- [x] 支持多种元数据格式（CSV/JSON/TXT，已完成）
- [ ] 添加断点续传功能
- [ ] 添加论文摘要和关键词提取
- [ ] 添加数据库存储功能
- [ ] 添加论文搜索和过滤功能

**注意**：
- IEEE S&P已实现自动下载功能，需要IEEE会员账号
- ACM CCS需要会员认证才能下载。如果您有ACM会员资格，可以提供用户名和密码，我们可以实现自动下载功能
- 如果没有会员资格，建议通过机构订阅、DBLP或作者个人主页获取论文

## 许可证

本项目仅供学习和研究使用。请遵守相关会议和论文的版权规定。

## 贡献

欢迎提交 Issue 和 Pull Request！

## 监控下载进度

提供了一个便捷的监控脚本：

```bash
# 查看爬虫状态和下载进度
./check_status.sh
```

该脚本会显示：
- 爬虫进程状态
- 各年份已下载的论文数量
- 最新的日志信息

或者直接查看日志文件：

```bash
# 查看NDSS爬虫日志
tail -f logs/ndss_download.log

# 查看USENIX Security爬虫日志
tail -f logs/usenix_download.log

# 查看IEEE S&P爬虫日志
tail -f logs/ieee_sp_download.log
```

## 后台运行

如果需要长时间下载，可以在后台运行：

```bash
# NDSS爬虫后台运行
nohup uv run python crawler_ndss.py -y 2021 2022 2023 2024 2025 --format csv --workers 10 > logs/ndss_download.log 2>&1 &

# USENIX Security爬虫后台运行
nohup uv run python crawler_usenix_security.py -y 2021 2022 2023 2024 2025 --format csv --workers 10 > logs/usenix_download.log 2>&1 &

# IEEE S&P爬虫后台运行（需要先设置环境变量）
export IEEE_USERNAME="your_username"
export IEEE_PASSWORD="your_password"
nohup uv run python crawler_ieee_sp.py -y 2021 2022 2023 2024 2025 --format csv --workers 10 > logs/ieee_sp_download.log 2>&1 &
```

## 联系方式

如有问题或建议，请通过 Issue 提交。

