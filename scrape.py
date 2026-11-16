import csv, os
from datetime import datetime, timezone, timedelta
import httpx

ID = "567563613"
DAILY = f"https://yobang.tencentmusic.com/unichartsapi/yobang/daily/chart/detail/all?itemId={ID}"
WEEKLY = f"https://yobang.tencentmusic.com/unichartsapi/v1/songs/{ID}/charts_detail"
HEAD = {"User-Agent": "Mozilla/5.0", "Referer": "https://yobang.tencentmusic.com/"}
COLS = ["时间", "榜单", "排名", "综合得分", "涨幅", "播放热度", "畅销度", "推荐度"]
BJ = timezone(timedelta(hours=8))


def get_daily(c):
    d = c.get(DAILY).json()["data"][0]
    e = d.get("extend") or {}
    return ["日榜", d["rank"], d["score"], d["incrScore"],
            e.get("playIndex", ""), e.get("payIndex", ""), e.get("popIndex", "")]


def get_weekly(c):
    d = c.get(WEEKLY).json()["data"][0]
    idx = {x["code"]: x["index"] for x in d.get("classifyIndices", [])}
    return ["周榜", d["curRank"], d["uniIndex"], d["indexThanPre"],
            idx.get(1, ""), idx.get(4, ""), idx.get(5, "")]


def save(path, row):
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(COLS)
        w.writerow([datetime.now(BJ).strftime("%Y/%m/%d %H:%M")] + row)
    print("写入", path, row)


with httpx.Client(headers=HEAD, timeout=20) as c:
    save("daily.csv", get_daily(c))
    save("weekly.csv", get_weekly(c))
