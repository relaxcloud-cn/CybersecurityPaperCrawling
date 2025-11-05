#!/bin/bash
# 检查爬虫下载状态和进度

echo "=== 爬虫进程状态 ==="
ps aux | grep -E "(crawler_ndss|crawler_usenix|crawler_ieee_sp)" | grep python | grep -v grep || echo "没有运行中的爬虫进程"
echo ""

echo "=== 已下载论文统计 ==="
for conf in NDSS USENIX_Security IEEE_SP; do
    echo ""
    echo "$conf:"
    total=0
    for year in 2021 2022 2023 2024 2025; do
        if [ -d "$conf/$year/papers" ]; then
            count=$(find "$conf/$year/papers" -name "*.pdf" 2>/dev/null | wc -l)
            if [ "$count" -gt 0 ]; then
                echo "  $year: $count 篇"
                total=$((total + count))
            fi
        fi
    done
    if [ "$total" -gt 0 ]; then
        echo "  总计: $total 篇"
    fi
done
echo ""

echo "=== NDSS爬虫最新日志 ==="
tail -5 logs/ndss_download.log 2>/dev/null || echo "日志文件不存在"
echo ""

echo "=== USENIX Security爬虫最新日志 ==="
tail -5 logs/usenix_download.log 2>/dev/null || echo "日志文件不存在"
echo ""

echo "=== IEEE S&P爬虫最新日志 ==="
tail -5 logs/ieee_sp_download.log 2>/dev/null || echo "日志文件不存在"
echo ""

echo "查看完整日志:"
echo "  tail -f logs/ndss_download.log"
echo "  tail -f logs/usenix_download.log"
echo "  tail -f logs/ieee_sp_download.log"

