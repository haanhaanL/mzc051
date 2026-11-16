import requests
import schedule
import time
import csv
import os
from datetime import datetime

# ========== 配置区 ==========
# 填入你浏览器里复制的完整 Cookie（首次运行用）
COOKIE = "SUB=_2AkMdSy--f8NxqwFRm_8WxW3lbYhyyw7EieKrF95lJRMxHRl-8z9yqlUBtRJ6NssBUYwX8dSB8KL3N42K05ky5ANRvnbA; SUBP=0033WrSXqPxfM72-Ws9jqgMF55529P9D9Wh0I2HwkW.pOhwQWukpuXlA"
USER_AGENT = "Mozilla/5.0 (Linux; Android 16; Pixel 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Mobile Safari/537.36"

TREND_URL = "https://m.s.weibo.com/ajax_topic/trend"
PARAMS = {"q": "#穆祉丞生日单曲阴天也会有烦恼吗#", "version": "v1", "time": "6m"}

# 用于保活的会话（保持 Cookie 自动更新）
session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT, "Referer": "https://m.s.weibo.com/"})

# 把初始 Cookie 填入 session
for item in COOKIE_STR.split("; "):
    if "=" in item:
        k, v = item.split("=", 1)
        session.cookies.set(k, v)


def refresh_cookie():
    """访问微博首页，让服务器通过 Set-Cookie 刷新短期令牌"""
    try:
        session.get("https://m.weibo.cn/", timeout=10)
        print(f"[{datetime.now()}] Cookie 保活刷新完成")
    except Exception as e:
        print(f"[{datetime.now()}] 保活刷新失败: {e}")


def crawl_and_save():
    """爬取趋势数据并追加到 CSV"""
    refresh_cookie()  # 先刷新，再爬取，降低因令牌过期失败的概率

    try:
        resp = session.get(TREND_URL, params=PARAMS, timeout=15)
        if resp.status_code != 200:
            print(f"[{datetime.now()}] 请求失败: {resp.status_code}")
            return

        data = resp.json()
        # 解析逻辑同之前脚本，这里简化为直接打印
        # 你需要根据实际返回的 JSON 结构提取互动趋势、原创趋势
        print(f"[{datetime.now()}] 爬取成功，数据长度: {len(str(data))}")

        # === 在这里追加写入 CSV ===
        # 示例：假设提取到 rows 列表
        # with open("weibo_trend.csv", "a", newline="", encoding="utf-8-sig") as f:
        #     writer = csv.writer(f)
        #     for row in rows:
        #         writer.writerow(row)

    except Exception as e:
        print(f"[{datetime.now()}] 爬取异常: {e}")


# ========== 调度配置 ==========
# 每10分钟爬一次
schedule.every(10).minutes.do(crawl_and_save)

# 启动时先跑一次，方便验证
crawl_and_save()

print("定时任务已启动，每10分钟执行一次。按 Ctrl+C 停止。")
while True:
    schedule.run_pending()
    time.sleep(1)
