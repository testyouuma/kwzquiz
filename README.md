# 棒バトフレームクイズ

棒バトLOD（https://aiueo9999.pythonanywhere.com/ ）の作品から動画の1フレームを出題し、
4択（作品名・作者・投稿日）でどの作品か当てる静的サイト。

## 構成

| ファイル | 役割 |
|----------|------|
| `build_dataset.py` | 全作品をスクレイピングして `works.json`（メタ情報）を作る |
| `extract_frames.py` | 各動画を360pで一時DL→ランダムなフレームを抽出。`quiz_data.json` と `frames/*.jpg` を作る |
| `index.html` | クイズ本体（静的サイト） |
| `works.json` | 作品カタログ（自動生成） |
| `quiz_data.json` | フレーム付き出題データ（自動生成） |
| `frames/` | 抽出したフレーム画像（自動生成） |

## セットアップ

```bash
python -m pip install yt-dlp imageio-ffmpeg Pillow
```

（ffmpegは `imageio-ffmpeg` に同梱されるのでインストール不要）

## 手順

### 1. カタログ作成（数分）
```bash
python build_dataset.py
```

### 2. フレーム抽出（長い・途中で止めても再開可）
```bash
python extract_frames.py            # 全作品
python extract_frames.py --limit 20 # お試し20件
python extract_frames.py --frames 5 # 1作品あたりのコマ数
```
- 全作品(約865本)で1〜2時間ほど。ネット環境次第。
- 中断しても、もう一度同じコマンドで**続きから**再開します。

### 3. ローカル確認
```bash
python -m http.server 8899
# ブラウザで http://127.0.0.1:8899/index.html
```

## GitHub Pages で公開

1. GitHubで新しいリポジトリ（例: `kwzquiz`）を作る
2. この `quiz/` の中身（`index.html` / `quiz_data.json` / `frames/`）をpush
3. リポジトリの Settings → Pages → Branch を `main` / `/root` に設定
4. `https://<ユーザー名>.github.io/kwzquiz/` で公開

> `works.json` や `*.py` は公開に必須ではないが、置いてあっても害はない。

## 仕組みメモ

- 動画DLは**事前抽出のときだけ**。公開サイトは静的画像を見せるだけなのでサーバー不要。
- 真っ黒・真っ白（ほぼ単色）のコマは抽出時に自動除外。それでも変なコマが出たら「別のコマ！」で切替。
- 投稿日・動画長は yt-dlp が取得した本物の値で補完済み。
