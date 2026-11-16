import csv, os
from datetime import datetime, timezone, timedelta
import httpx

ID = "567563613"
DAILY = f"https://yobang.tencentmusic.com/unichartsapi/yobang/daily/chart/detail/all?itemId={ID}"
WEEKLY = f"https://yobang.tencentmusic.com/unichartsapi/v1/songs/{ID}/charts_detail"
HEAD = {"User-Agent": "Mozilla/5.0", "Referer": "https://yobang.tencentmusic.com/"}
COLS = ["时间", "榜单", "排名", "综合得分", "涨幅", "播放热度", "畅销度", "推荐度",
        "播放热度涨幅", "畅销度涨幅", "推荐度涨幅"]
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
    last = read_last_row(path, row["榜单"])

    score_change = (row.get("涨幅") or "").strip()
    if not score_change and last:
        score_change = calc_delta(row["综合得分"], last.get("综合得分"))

    now = datetime.now(BJ)
    is_daily_0606 = (
        row["榜单"] == "日榜"
        and now.hour == 6
        and now.minute == 6
    )

    dim_changes = {}
    for d in DIMS:
        if is_daily_0606:
            dim_changes[d] = "-"
        else:
            dim_changes[d] = calc_delta(row[d], last.get(d)) if last else ""

    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(COLS)
        w.writerow([
            now.strftime("%Y/%m/%d %H:%M"),
            row["榜单"], row["排名"], row["综合得分"], score_change,
            row["播放热度"], row["畅销度"], row["推荐度"],
            dim_changes["播放热度"], dim_changes["畅销度"], dim_changes["推荐度"],
        ])
    print("写入", path, row["榜单"], row["综合得分"], score_change)


with httpx.Client(headers=HEAD, timeout=20) as c:
    save("daily.csv", get_daily(c))
    save("weekly.csv", get_weekly(c))
