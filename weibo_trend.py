import requests
import csv
import os
import json
from datetime import datetime, timedelta

# ============================================================
# 配置区
# ============================================================
COOKIE_FILE = "weibo_cookie.json"   # Cookie 持久化文件
CSV_FILE = "weibo_trend.csv"

TREND_URL = "https://m.s.weibo.com/ajax_topic/trend"
PARAMS = {"q": "#穆祉丞生日单曲阴天也会有烦恼吗#", "version": "v1", "time": "6m"}

BASE_FIELDS = ["时间", "阅读量", "讨论量", "互动量", "原创量"]
FIELDS = BASE_FIELDS + ["阅读量_修正", "讨论量_修正", "互动量_修正", "原创量_修正"]

METRIC_MAP = {
    "read": "阅读量",
    "me": "讨论量",
    "partake": "互动量",
    "ori": "原创量",
}

# 首次运行用的初始 Cookie / UA（仅当 cookie 文件不存在时使用）
INIT_COOKIE = "在这里粘贴你的完整 Cookie"
USER_AGENT = "在这里粘贴你的 User-Agent"


# ============================================================
# Cookie 持久化
# ============================================================
def load_cookie():
    """优先从文件读 Cookie，没有则用初始值"""
    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"cookie": INIT_COOKIE, "user_agent": USER_AGENT}


def save_cookie(sess):
    """把当前 session 的 Cookie 存到文件"""
    cookies = {c.name: c.value for c in sess.cookies}
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump({"cookie": cookies, "user_agent": sess.headers.get("User-Agent", USER_AGENT)},
                  f, ensure_ascii=False, indent=2)


def build_session(cookie_data):
    """根据 cookie 数据构造 session"""
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": cookie_data.get("user_agent", USER_AGENT),
        "Referer": "https://m.s.weibo.com/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    cookie = cookie_data.get("cookie", "")
    if isinstance(cookie, str):
        # 兼容首次的字符串格式
        for item in cookie.split("; "):
            if "=" in item:
                k, v = item.split("=", 1)
                sess.cookies.set(k, v)
    elif isinstance(cookie, dict):
        for k, v in cookie.items():
            sess.cookies.set(k, v)
    return sess


def refresh_cookie(sess):
    """访问微博首页刷新短期令牌，然后持久化"""
    try:
        sess.get("https://m.weibo.cn/", timeout=10)
        save_cookie(sess)
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Cookie 已刷新并保存")
    except Exception as e:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 保活刷新失败: {e}")


# ============================================================
# 时间处理
# ============================================================
def resolve_date(time_str, now=None):
    now = now or datetime.now()
    hh, mm = map(int, time_str.split(":"))
    candidate = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if candidate > now:
        candidate -= timedelta(days=1)
    return candidate.strftime("%Y-%m-%d %H:%M")


# ============================================================
# CSV 读写
# ============================================================
def load_existing(filename):
    if not os.path.exists(filename):
        return {}
    existing = {}
    with open(filename, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("时间"):
                existing[row["时间"]] = row
    return existing


def parse_trend(data, now=None):
    merged = {}
    for key, col in METRIC_MAP.items():
        for item in data.get(key, []):
            t = item.get("time")
            if not t:
                continue
            full_time = resolve_date(t, now)
            if full_time not in merged:
                merged[full_time] = {f: "" for f in BASE_FIELDS}
                merged[full_time]["时间"] = full_time
            merged[full_time][col] = item.get("value", "")
    return [merged[t] for t in sorted(merged.keys())]


def upsert_rows(rows, filename=CSV_FILE):
    existing = load_existing(filename)
    new_rows = []
    updated_rows = {}

    for r in rows:
        t = r["时间"]
        if t not in existing:
            full = {f: "" for f in FIELDS}
            full.update(r)
            new_rows.append(full)
        else:
            old = existing[t]
            changed = False
            for col in ["阅读量", "讨论量", "互动量", "原创量"]:
                new_val = str(r.get(col, ""))
                old_val = str(old.get(col, ""))
                if new_val and new_val != old_val:
                    old[col + "_修正"] = new_val
                    changed = True
            if changed:
                updated_rows[t] = old

    if new_rows:
        file_exists = os.path.exists(filename)
        with open(filename, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            if not file_exists:
                writer.writeheader()
            writer.writerows(new_rows)

    if updated_rows:
        all_rows = []
        for t, row in existing.items():
            all_rows.append(updated_rows.get(t, row))
        all_rows.extend(new_rows)
        all_rows.sort(key=lambda x: x["时间"])
        with open(filename, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(all_rows)

    print(f"新增 {len(new_rows)} 行，修正 {len(updated_rows)} 行")


# ============================================================
# 主流程（一次性执行）
# ============================================================
def main():
    cookie_data = load_cookie()
    sess = build_session(cookie_data)
    refresh_cookie(sess)

    try:
        resp = sess.get(TREND_URL, params=PARAMS, timeout=15)
        if resp.status_code != 200:
            print(f"请求失败: {resp.status_code}, {resp.text[:200]}")
            return
        data = resp.json()
        rows = parse_trend(data)
        if not rows:
            print("未解析到趋势数据")
            return
        upsert_rows(rows)
    except Exception as e:
        print(f"爬取异常: {e}")


if __name__ == "__main__":
    main()
