import csv, os, re
from datetime import datetime, timezone, timedelta
import httpx

ID = "567563613"
DAILY = f"https://yobang.tencentmusic.com/unichartsapi/yobang/daily/chart/detail/all?itemId={ID}"
WEEKLY = f"https://yobang.tencentmusic.com/unichartsapi/v1/songs/{ID}/charts_detail"
HEAD = {"User-Agent": "Mozilla/5.0", "Referer": "https://yobang.tencentmusic.com/"}

COLS_DAILY = ["时间", "榜单", "排名", "综合得分", "涨幅",
              "播放热度", "播放热度涨幅",
              "畅销度", "畅销度涨幅",
              "推荐度", "推荐度涨幅"]
COLS_WEEKLY = COLS_DAILY + ["综合得分原值", "综合原值涨幅"]

BJ = timezone(timedelta(hours=8))
DIMS = ["播放热度", "畅销度", "推荐度"]


def get_daily(c):
    d = c.get(DAILY).json()["data"][0]
    e = d.get("extend") or {}
    return {
        "榜单": "日榜",
        "排名": d["rank"],
        "综合得分": d["score"],
        "涨幅": d["incrScore"],
        "播放热度": e.get("playIndex", ""),
        "畅销度": e.get("payIndex", ""),
        "推荐度": e.get("popIndex", ""),
    }


def get_weekly(c):
    d = c.get(WEEKLY).json()["data"][0]
    idx = {x["code"]: x["index"] for x in d.get("classifyIndices", [])}
    return {
        "榜单": "周榜",
        "排名": d["curRank"],
        "综合得分": d["uniIndex"],
        "涨幅": d["indexThanPre"],
        "播放热度": idx.get(1, ""),
        "畅销度": idx.get(4, ""),
        "推荐度": idx.get(5, ""),
        "综合得分原值": d.get("uniIndexNew", ""),
    }


def read_last_row(path, chart_type):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in reversed(rows):
        if r.get("榜单") == chart_type:
            return r
    return None


def calc_delta(cur, prev):
    try:
        a = float(cur)
        b = float(prev)
        return f"{a - b:.2f}"
    except (TypeError, ValueError):
        return ""


def save(path, row):
    is_daily = row["榜单"] == "日榜"
    cols = COLS_DAILY if is_daily else COLS_WEEKLY
    last = read_last_row(path, row["榜单"])

    now = datetime.now(BJ)
    is_early_daily = (
        is_daily
        and (now.hour, now.minute) >= (0, 26)
        and (now.hour, now.minute) <= (5, 56)
    )

    score_change = (row.get("涨幅") or "").strip()
    if is_early_daily:
        if not score_change:
            score_change = "0.00"
    else:
        if not score_change and last:
            score_change = calc_delta(row["综合得分"], last.get("综合得分"))

    is_daily_0606 = is_daily and now.hour == 6 and now.minute == 6

    dim_changes = {}
    for d in DIMS:
        if is_daily_0606:
            dim_changes[d] = "-"
        else:
            dim_changes[d] = calc_delta(row[d], last.get(d)) if last else ""

    raw_change = ""
    if not is_daily and last:
        raw_change = calc_delta(row.get("综合得分原值", ""), last.get("综合得分原值"))

    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(cols)
        out = [
            now.strftime("%Y/%m/%d %H:%M"),
            row["榜单"], row["排名"], row["综合得分"], score_change,
            row["播放热度"], dim_changes["播放热度"],
            row["畅销度"], dim_changes["畅销度"],
            row["推荐度"], dim_changes["推荐度"],
        ]
        if not is_daily:
            out.append(row.get("综合得分原值", ""))
            out.append(raw_change)
        w.writerow(out)
    print("写入", path, row["榜单"], row["综合得分"], score_change)


# ========== 自动生成 combined_06.csv ==========
COMBINED_06 = "combined_06.csv"
COMBINED_06_COLS = COLS_WEEKLY


def _parse_time(s):
    m = re.search(r"(\d{4})/(\d{2})/(\d{2})\s+(\d{1,2}):(\d{2})", s or "")
    if not m:
        return None
    return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                    int(m.group(4)), int(m.group(5)))


def _read_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for c in COMBINED_06_COLS:
            r[c] = r.get(c) or ""
        r["_dt"] = _parse_time(r.get("时间", ""))
    return [r for r in rows if r["_dt"]]


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _delta(cur, prev):
    a = _to_float(cur)
    b = _to_float(prev)
    if a is None or b is None:
        return ""
    return f"{a - b:.2f}"


def _is_monday_026(dt):
    return dt.weekday() == 0 and dt.hour == 0 and dt.minute == 26


def _is_monday_106(dt):
    return dt.weekday() == 0 and dt.hour == 1 and dt.minute == 6


def _is_six_six(dt):
    return dt.hour == 6 and dt.minute == 6


def _build_daily_06(rows):
    """日榜：只取 06 分，6:06 读官方涨幅，其余与前一条 06 分作差"""
    rows = sorted([r for r in rows if r["_dt"].minute == 6], key=lambda r: r["_dt"])
    out = []
    prev = None
    for r in rows:
        dt = r["_dt"]
        rec = {c: r.get(c, "") for c in COMBINED_06_COLS}
        rec["时间"] = r.get("时间", "")
        rec["榜单"] = "日榜"

        if _is_six_six(dt):
            rec["涨幅"] = r.get("涨幅", "")
            for d in DIMS:
                rec[f"{d}涨幅"] = r.get(f"{d}涨幅", "")
        else:
            if prev is None:
                rec["涨幅"] = ""
                for d in DIMS:
                    rec[f"{d}涨幅"] = ""
            else:
                rec["涨幅"] = _delta(r.get("综合得分"), prev.get("综合得分"))
                for d in DIMS:
                    rec[f"{d}涨幅"] = _delta(r.get(d), prev.get(d))

        out.append(rec)
        prev = r
    return out


def _build_weekly_06(rows):
    """
    周榜：只取 06 分。
    周一 1:06 与周一 0:26 作差（0:26 从 weekly.csv 找，不进入输出）。
    其余 06 分与前一条 06 分作差。
    """
    rows_all = sorted(rows, key=lambda r: r["_dt"])
    rows_06 = [r for r in rows_all if r["_dt"].minute == 6]

    monday_026 = {}
    for r in rows_all:
        if _is_monday_026(r["_dt"]):
            monday_026[r["_dt"].date()] = r

    out = []
    prev = None
    for r in rows_06:
        dt = r["_dt"]
        rec = {c: r.get(c, "") for c in COMBINED_06_COLS}
        rec["时间"] = r.get("时间", "")
        rec["榜单"] = "周榜"

        if _is_monday_106(dt):
            base = monday_026.get(dt.date())
            if base:
                rec["涨幅"] = _delta(r.get("综合得分"), base.get("综合得分"))
                for d in DIMS:
                    rec[f"{d}涨幅"] = _delta(r.get(d), base.get(d))
                rec["综合原值涨幅"] = _delta(r.get("综合得分原值"), base.get("综合得分原值"))
            else:
                rec["涨幅"] = r.get("涨幅", "")
                for d in DIMS:
                    rec[f"{d}涨幅"] = r.get(f"{d}涨幅", "")
                rec["综合原值涨幅"] = ""
        else:
            if prev is None:
                rec["涨幅"] = ""
                for d in DIMS:
                    rec[f"{d}涨幅"] = ""
                rec["综合原值涨幅"] = ""
            else:
                rec["涨幅"] = _delta(r.get("综合得分"), prev.get("综合得分"))
                for d in DIMS:
                    rec[f"{d}涨幅"] = _delta(r.get(d), prev.get(d))
                rec["综合原值涨幅"] = _delta(r.get("综合得分原值"), prev.get("综合得分原值"))

        out.append(rec)
        prev = r
    return out


def export_combined_06():
    daily_rows = _read_rows("daily.csv")
    weekly_rows = _read_rows("weekly.csv")

    daily_06 = _build_daily_06(daily_rows)
    weekly_06 = _build_weekly_06(weekly_rows)

    by_time = {}
    for rec in daily_06:
        by_time.setdefault(rec["时间"], {})["日榜"] = rec
    for rec in weekly_06:
        by_time.setdefault(rec["时间"], {})["周榜"] = rec

    merged = []
    for key in sorted(by_time.keys(), key=lambda k: _parse_time(k) or datetime.min):
        group = by_time[key]
        if "日榜" in group:
            merged.append(group["日榜"])
        if "周榜" in group:
            merged.append(group["周榜"])

    with open(COMBINED_06, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COMBINED_06_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(merged)

    print(f"写入 {COMBINED_06}，共 {len(merged)} 行（日榜 {len(daily_06)} 条，周榜 {len(weekly_06)} 条）")


# ========== 主流程 ==========
with httpx.Client(headers=HEAD, timeout=20) as c:
    save("daily.csv", get_daily(c))
    save("weekly.csv", get_weekly(c))

# 每次运行都重新生成 combined_06.csv（全量覆盖）
try:
    export_combined_06()
except Exception as e:
    print("combined_06.csv 生成失败：", e)
