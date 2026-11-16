import os
import csv
import requests
from datetime import datetime, timedelta, timezone

# ============================================================
# 配置区
# ============================================================
INIT_COOKIE = os.environ.get("WEIBO_COOKIE", "")
USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"

TREND_URL = "https://m.s.weibo.com/ajax_topic/trend"
PARAMS = {"q": "#穆祉丞生日单曲阴天也会有烦恼吗#", "version": "v1", "time": "24h"}

CSV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weibo_trend.csv")

FIELDS = ["时间", "阅读量", "讨论量", "互动量", "原创量"]

METRIC_MAP = {
    "read": "阅读量",
    "me": "讨论量",
    "partake": "互动量",
    "ori": "原创量",
}

ENABLE_REFRESH = True

# 北京时间时区
BJT = timezone(timedelta(hours=8))


# ============================================================
# 构建 session
# ============================================================
def build_session():
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": USER_AGENT,
        "Referer": "https://m.s.weibo.com/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    for item in INIT_COOKIE.split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            sess.cookies.set(k.strip(), v.strip())
    print(f"已加载 {len(sess.cookies)} 个 Cookie 字段: {list(sess.cookies.keys())}")
    return sess


def refresh_cookie(sess):
    try:
        sess.get("https://m.weibo.cn/", timeout=10)
        print(f"[{datetime.now(BJT):%Y-%m-%d %H:%M:%S}] Cookie 保活刷新完成")
    except Exception as e:
        print(f"[{datetime.now(BJT):%Y-%m-%d %H:%M:%S}] 保活刷新失败: {e}")


# ============================================================
# 时间处理
# ============================================================
def resolve_date(time_str, now=None):
    """
    把 HH:MM 解析成北京时间 YYYY-MM-DD HH:MM。
    接口 time=24h 返回过去 24 小时刻度：
    - HH:MM 不晚于当前时刻 -> 今天；
    - HH:MM 晚于当前时刻 -> 昨天（窗口回溯，不可能是未来）。
    """
    now = now or datetime.now(BJT)
    hh, mm = map(int, time_str.split(":"))
    candidate = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if candidate > now:
        candidate -= timedelta(days=1)
    return candidate.strftime("%Y-%m-%d %H:%M")


# ============================================================
# CSV 读写
# ============================================================
def load_existing(filename):
    """读取已有 CSV，按时间去重（同时间只保留第一次出现的行）"""
    if not os.path.exists(filename):
        return {}
    existing = {}
    with open(filename, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            t = row.get("时间")
            if t and t not in existing:
                existing[t] = {
                    "时间": t,
                    "阅读量": row.get("阅读量", ""),
                    "讨论量": row.get("讨论量", ""),
                    "互动量": row.get("互动量", ""),
                    "原创量": row.get("原创量", ""),
                }
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
                merged[full_time] = {f: "" for f in FIELDS}
                merged[full_time]["时间"] = full_time
            merged[full_time][col] = item.get("value", "")
    return [merged[t] for t in sorted(merged.keys())]


def upsert_rows(rows, filename=CSV_FILE):
    """
    规则：
    - 时间不存在 -> 新增；
    - 时间已存在且是同一天 -> 用最新值覆盖；
    - 时间已存在但跨天 -> 保留旧日期不动。
    保证文件开头有表头。
    """
    existing = load_existing(filename)
    new_rows = []
    updated_count = 0

    # 本次抓取内部按时间去重，同时间保留第一次出现
    seen = set()
    for r in rows:
        t = r["时间"]
        if t in seen:
            continue
        seen.add(t)

        if t in existing:
            old = existing[t]
            if t[:10] == old["时间"][:10]:
                # 同一天：用最新值覆盖
                new_row = {f: r.get(f, "") for f in FIELDS}
                new_row["时间"] = t
                if new_row != old:
                    existing[t] = new_row
                    updated_count += 1
            # 跨天：保留旧值，不动
            continue

        new_rows.append({f: r.get(f, "") for f in FIELDS})

    # 判断是否需要补表头：文件不存在 / 为空 / 第一行不是表头
    need_header = True
    if os.path.exists(filename) and os.path.getsize(filename) > 0:
        with open(filename, "r", encoding="utf-8-sig") as f:
            first_line = f.readline().lstrip("\ufeff").strip()
        need_header = first_line != ",".join(FIELDS)

    if need_header or updated_count:
        # 有表头修复或同天覆盖 -> 重写整个文件
        all_rows = list(existing.values()) + new_rows
        all_rows.sort(key=lambda x: x["时间"])
        with open(filename, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(all_rows)
    elif new_rows:
        with open(filename, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writerows(new_rows)

    ignored = len(seen) - len(new_rows) - updated_count
    print(f"新增 {len(new_rows)} 行，同天覆盖 {updated_count} 个，忽略 {ignored} 个")
    print(f"CSV 文件路径: {filename}")
    return len(new_rows), updated_count


# ============================================================
# 主流程
# ============================================================
def main():
    if not INIT_COOKIE:
        print("[错误] 环境变量 WEIBO_COOKIE 为空，请检查 GitHub Actions Secrets 配置")
        return

    sess = build_session()
    if ENABLE_REFRESH:
        refresh_cookie(sess)

    try:
        resp = sess.get(TREND_URL, params=PARAMS, timeout=15)
        print(f"HTTP 状态码: {resp.status_code}")

        if resp.status_code != 200:
            print(f"请求失败: {resp.status_code}, 返回前 300 字符: {resp.text[:300]}")
            return

        resp_json = resp.json()
        print(f"接口返回顶层键: {list(resp_json.keys()) if isinstance(resp_json, dict) else type(resp_json)}")

        if not isinstance(resp_json, dict):
            print("返回不是 JSON 对象，原始内容前 500 字符:")
            print(resp.text[:500])
            return

        inner_data = resp_json.get("data", {})
        if not isinstance(inner_data, dict):
            print(f"返回的 data 字段不是对象: {inner_data!r}")
            print(f"原始返回前 500 字符: {resp.text[:500]}")
            return

        for k in METRIC_MAP:
            v = inner_data.get(k)
            print(f"  {k}: {len(v) if isinstance(v, list) else v!r} 条")

        rows = parse_trend(inner_data)
        if not rows:
            print("未解析到趋势数据，接口原始返回前 500 字符:")
            print(resp.text[:500])
            return

        print(f"解析到 {len(rows)} 行趋势数据")
        upsert_rows(rows)
    except Exception as e:
        print(f"爬取异常: {e}")
        try:
            print(f"响应内容前 300 字符: {resp.text[:300]}")
        except Exception:
            pass


if __name__ == "__main__":
    main()
