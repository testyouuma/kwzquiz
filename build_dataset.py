# build_dataset.py
# 棒バトLODの全作品(Q1..MAX)をスクレイピングして works.json を作る。
# 動画DLは不要。出題に使うメタデータ（作品名/作者/投稿日/動画URL/長さ）を集める。

import sys
import re
import json
import html as htmllib
import urllib.request
import concurrent.futures
from pathlib import Path

BASE = "https://aiueo9999.pythonanywhere.com/detail/Q{}"
MAX_ID = 1600
OUT = Path(__file__).parent / "works.json"

sys.stdout.reconfigure(encoding="utf-8")


def clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    s = htmllib.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def parse(n: int, html: str):
    # タイトル（h1のアイコンの後ろ）
    tm = re.search(r"<h1[^>]*>.*?<i[^>]*></i>\s*(.+?)\s*</h1>", html, re.DOTALL)
    title = clean(tm.group(1)) if tm else f"Q{n}"

    # ラベル/値ペア
    fields = {}
    for m in re.finditer(
        r'<td class="wb-label">(.*?)</td>\s*<td class="wb-value">(.*?)</td>',
        html, re.DOTALL,
    ):
        label = clean(m.group(1))
        fields[label] = m.group(2)  # 生HTMLのまま（後で用途別に処理）

    def field_text(key):
        for k, v in fields.items():
            if k.startswith(key):
                return clean(v)
        return ""

    author = field_text("作者")
    date = field_text("投稿日")
    duration = field_text("動画時間")

    # 動画URL
    yt = re.search(r"youtube\.com/embed/([a-zA-Z0-9_-]+)", html)
    nico = re.search(r"nicovideo\.jp/watch/(sm\d+)", html)
    if yt:
        platform, vid = "youtube", yt.group(1)
        url = f"https://www.youtube.com/watch?v={vid}"
    elif nico:
        platform, vid = "niconico", nico.group(1)
        url = f"https://www.nicovideo.jp/watch/{vid}"
    else:
        return None  # 動画なしはクイズに使えない

    return {
        "id": f"Q{n}",
        "title": title,
        "author": author or "不明",
        "date": date,
        "duration": duration,
        "platform": platform,
        "video_id": vid,
        "url": url,
    }


def fetch(n: int):
    try:
        html = urllib.request.urlopen(BASE.format(n), timeout=20).read().decode("utf-8", errors="replace")
    except Exception:
        return None
    if "wb-label" not in html:
        return None
    try:
        return parse(n, html)
    except Exception as e:
        print(f"Q{n} parse error: {e}")
        return None


def main():
    works = []
    ids = list(range(1, MAX_ID + 1))
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        for res in ex.map(fetch, ids):
            done += 1
            if res:
                works.append(res)
            if done % 50 == 0:
                print(f"  {done}/{len(ids)}  (集まった: {len(works)})")

    works.sort(key=lambda w: int(w["id"][1:]))
    OUT.write_text(json.dumps(works, ensure_ascii=False, indent=2), encoding="utf-8")

    yt = sum(1 for w in works if w["platform"] == "youtube")
    nico = sum(1 for w in works if w["platform"] == "niconico")
    print(f"\n完了: {len(works)}件  (YouTube {yt} / ニコニコ {nico})")
    print(f"出力: {OUT}")


if __name__ == "__main__":
    main()
