# extract_frames.py
# works.json の各作品について、動画を360pで一時DLし、
# ランダム位置のフレームを複数抽出する。真っ黒/真っ白（ほぼ単色）は自動除外。
# 本物の投稿日・動画長も yt-dlp から取得して補完する。
#
# 途中で止めても再開可能（既にフレームがある作品はスキップ）。
#
# 必要: yt-dlp, imageio-ffmpeg, Pillow
#   python -m pip install yt-dlp imageio-ffmpeg Pillow
#
# 使い方:
#   python extract_frames.py              # 全部
#   python extract_frames.py --limit 20   # 先頭20件だけ（お試し）
#   python extract_frames.py --frames 5   # 1作品あたり残すフレーム数

import sys
import os
import json
import random
import argparse
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageStat

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).parent
WORKS = HERE / "works.json"
OUT = HERE / "quiz_data.json"
FRAME_DIR = HERE / "frames"
FF = imageio_ffmpeg.get_ffmpeg_exe()

# 候補として抜く枚数（この中から良いものを選ぶ）
CANDIDATES = 12
# 残すフレーム数（デフォルト）
KEEP_DEFAULT = 5
# 単色判定：グレースケール標準偏差がこれ未満なら「のっぺり（黒/白/単色）」として除外
STDDEV_MIN = 18.0
# フレーム幅
FRAME_W = 480


def run(cmd, timeout=180):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def get_info(url):
    r = run(["python", "-m", "yt_dlp", "-J", "--no-warnings", url], timeout=90)
    if r.returncode != 0:
        return None
    try:
        info = json.loads(r.stdout)
    except Exception:
        return None
    return {
        "duration": info.get("duration"),
        "upload_date": info.get("upload_date"),  # YYYYMMDD
        "title": info.get("title"),
        "uploader": info.get("uploader"),
    }


def download_360p(url, dest_noext):
    fmt = ("video-h264-360p-0/video-h264-360p-1/"
           "bestvideo[height<=360][ext=mp4]/best[height<=360]/best")
    # 通常 → ダメなら player_client を切替えて403回避（YouTube対策）
    attempts = [
        [],
        ["--extractor-args", "youtube:player_client=android"],
        ["--extractor-args", "youtube:player_client=tv"],
    ]
    r = None
    for extra in attempts:
        r = run(["python", "-m", "yt_dlp", "--ffmpeg-location", FF,
                 "-f", fmt, "-o", f"{dest_noext}.%(ext)s",
                 "--no-warnings", "--no-playlist", *extra, url], timeout=300)
        if r.returncode == 0:
            break
    if not r or r.returncode != 0:
        return None
    d = Path(dest_noext).parent
    for f in d.iterdir():
        if f.stem == Path(dest_noext).name:
            return f
    return None


def grab_frame(video, t, out_path):
    r = run([FF, "-y", "-ss", f"{t:.2f}", "-i", str(video),
             "-frames:v", "1", "-q:v", "3",
             "-vf", f"scale={FRAME_W}:-1", str(out_path)], timeout=60)
    return r.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0


def score_frame(path):
    # グレースケールの標準偏差（大きいほど内容が豊富）。単色なら小さい。
    try:
        im = Image.open(path).convert("L")
        return ImageStat.Stat(im).stddev[0]
    except Exception:
        return 0.0


def extract_for_work(work, keep):
    dur = work.get("_real_duration")
    if not dur or dur < 3:
        return []

    with tempfile.TemporaryDirectory(prefix="kwzq_") as td:
        td = Path(td)
        video = download_360p(work["url"], str(td / "v"))
        if not video:
            return []

        # 候補タイムスタンプ（10%〜90%を均等割り＋ゆらぎ）
        cand = []
        for i in range(CANDIDATES):
            base = 0.10 + 0.80 * (i / max(1, CANDIDATES - 1))
            jitter = random.uniform(-0.03, 0.03)
            cand.append(max(0.5, min(dur - 0.5, dur * (base + jitter))))

        scored = []
        for i, t in enumerate(cand):
            tmp = td / f"c{i}.jpg"
            if grab_frame(video, t, tmp):
                s = score_frame(tmp)
                scored.append((s, t, tmp))

        # 単色除外
        good = [x for x in scored if x[0] >= STDDEV_MIN]
        if not good:  # 全部のっぺりなら仕方なくスコア上位を使う
            good = sorted(scored, reverse=True)[:keep]

        # 時系列に散らして keep 枚選ぶ（スコア順ではなく時間で分散）
        good.sort(key=lambda x: x[1])  # 時間順
        if len(good) > keep:
            step = len(good) / keep
            good = [good[int(i * step)] for i in range(keep)]

        # 保存
        saved = []
        for idx, (_s, _t, tmp) in enumerate(good):
            dst = FRAME_DIR / f"{work['id']}_{idx}.jpg"
            dst.write_bytes(tmp.read_bytes())
            saved.append(dst.name)
        return saved


def fmt_date(yyyymmdd):
    if yyyymmdd and len(yyyymmdd) == 8:
        return f"{yyyymmdd[0:4]}/{yyyymmdd[4:6]}/{yyyymmdd[6:8]}"
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="先頭N件だけ処理（0=全部）")
    ap.add_argument("--frames", type=int, default=KEEP_DEFAULT, help="1作品あたり残すフレーム数")
    ap.add_argument("--shuffle", action="store_true", help="処理順をランダムに")
    ap.add_argument("--retry-failed", action="store_true", help="フレーム抽出に失敗した作品だけ再挑戦")
    args = ap.parse_args()

    FRAME_DIR.mkdir(exist_ok=True)
    works = json.loads(WORKS.read_text(encoding="utf-8"))

    # 既存の成果を読み込み（再開用）
    data = {}
    if OUT.exists():
        for w in json.loads(OUT.read_text(encoding="utf-8")):
            data[w["id"]] = w

    if args.retry_failed:
        # 未処理 + フレームが空（＝前回失敗）の作品を対象
        todo = [w for w in works if w["id"] not in data or not data[w["id"]].get("frames")]
    else:
        todo = [w for w in works if w["id"] not in data]
    if args.shuffle:
        random.shuffle(todo)
    if args.limit:
        todo = todo[:args.limit]

    print(f"対象: {len(todo)}件（既完了 {len(data)}件）")

    for i, work in enumerate(todo, 1):
        info = get_info(work["url"])
        if info:
            work["_real_duration"] = info.get("duration")
            real_date = fmt_date(info.get("upload_date"))
            if real_date:
                work["date"] = real_date
            if info.get("duration"):
                m, s = divmod(int(info["duration"]), 60)
                work["duration"] = f"{m}:{s:02d}"

        try:
            frames = extract_for_work(work, args.frames)
        except Exception as e:
            print(f"[{i}/{len(todo)}] {work['id']} エラー: {e}")
            frames = []

        rec = {k: v for k, v in work.items() if not k.startswith("_")}
        rec["frames"] = frames
        data[work["id"]] = rec

        status = f"{len(frames)}枚" if frames else "×失敗"
        print(f"[{i}/{len(todo)}] {work['id']} {work['title'][:24]} -> {status}")

        # 逐次保存（途中で止めても大丈夫）
        out_list = [data[k] for k in sorted(data, key=lambda x: int(x[1:]))]
        OUT.write_text(json.dumps(out_list, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = sum(1 for w in data.values() if w.get("frames"))
    print(f"\n完了: フレームあり {ok}件 / 全{len(data)}件")
    print(f"データ: {OUT}")
    print(f"画像: {FRAME_DIR}")


if __name__ == "__main__":
    main()
