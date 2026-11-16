import os
import csv
import requests
from datetime import datetime, timedelta

# ============================================================
# 配置区
# ============================================================
# Cookie 从 GitHub Actions Secrets 注入，不在代码里写死
INIT_COOKIE = os.environ.get("WEIBO_COOKIE", "")
USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"

TREND_URL = "https://m.s.weibo.com/ajax_topic/trend"
PARAMS = {"q": "#穆祉丞生日单曲阴天也会有烦恼吗#", "version": "v1", "time": "6m"}

# 绝对路径，避免 Actions 工作目录不一致
CSV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weibo_trend.csv")

BASE_FIELDS = ["时间", "阅读量", "讨论量", "互动量", "原创量"]
FIELDS = BASE_FIELDS + ["阅读量_修正", "讨论量_修正", "互动量_修正", "原创量_修正"]

METRIC_MAP = {
    "read": "阅读量",
    "me": "讨论量",
    "partake": "互动量",
    "ori": "原创量",
}

# Actions 里建议开启，刷新短期令牌
ENABLE_REFRESH = True


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
    # 兼容 "; " 和 ";" 两种分隔
    for item in INIT_COOKIE.split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            sess.cookies.set(k.strip(), v.strip())
    print(f"已加载 {len(sess.cookies)} 个 Cookie 字段: {list(sess.cookies.keys())}")
    return sess


def refresh_cookie(sess):
    """访问微博首页，让服务器通过 Set-Cookie 刷新短期令牌（仅本次运行内有效）"""
    try:
        sess.get("https://m.weibo.cn/", timeout=10)
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Cookie 保活刷新完成")
    except Exception as e:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 保活刷新失败: {e}")


# ============================================================
# 时间处理
# ============================================================
def resolve_date(time_str, now=None):
    """
    把 HH:MM 解析成 YYYY-MM-DD HH:MM。
    若 HH:MM 大于当前时刻，视为前一天（处理跨午夜窗口）。
    """
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
    """
    data 是接口返回里的内层 data，形如：
    {"read":[...], "me":[...], "ori":[...], "partake":[...]}
    """
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
    """
    新增：时间不存在 -> 追加一行（修正列为空）
    修正：时间已存在但数值变了 -> 原行不动，新值写入对应 _修正 列
    同时保证文件开头一定有表头。
    """
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

    # 判断文件是否需要补表头：不存在 / 为空 / 第一行不是表头
    need_header = True
    if os.path.exists(filename) and os.path.getsize(filename) > 0:
        with open(filename, "r", encoding="utf-8-sig") as f:
            first_line = f.readline().lstrip("\ufeff").strip()
        need_header = first_line != ",".join(FIELDS)

    # 需要补表头，或者有修正行 -> 重写整个文件
    if need_header or updated_rows:
        all_rows = []
        for t, row in existing.items():
            all_rows.append(updated_rows.get(t, row))
        all_rows.extend(new_rows)
        all_rows.sort(key=lambda x: x["时间"])
        with open(filename, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(all_rows)
    elif new_rows:
        # 文件已有正确表头且无修正 -> 直接追加
        with open(filename, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writerows(new_rows)

    print(f"新增 {len(new_rows)} 行，修正 {len(updated_rows)} 行")
    print(f"CSV 文件路径: {filename}")
    return len(new_rows), len(updated_rows)


# ============================================================
# 主流程（一次性执行）
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

        # 关键：真正的指标数据在 resp_json["data"] 里
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
