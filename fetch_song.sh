#!/usr/bin/env bash
# Download the official upload (cosMo@暴走P, Bilibili BV1sb411M7be) into assets/song.mp3.
# The MV's timeline is calibrated against this exact 4:50 version.
set -euo pipefail
cd "$(dirname "$0")"

for tool in yt-dlp ffmpeg curl; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "缺少 $tool。安装方法：" >&2
    echo "  macOS:  brew install yt-dlp ffmpeg" >&2
    echo "  Ubuntu: sudo apt install ffmpeg curl pipx && pipx install yt-dlp" >&2
    exit 1
  fi
done

mkdir -p assets
if [ -f assets/song.mp3 ]; then
  echo "assets/song.mp3 已存在，跳过下载。"
else
  UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
  JAR="$(mktemp)"
  trap 'rm -f "$JAR"' EXIT
  curl -s -A "$UA" -c "$JAR" https://www.bilibili.com/ -o /dev/null || true
  echo "正在从 Bilibili 官方投稿下载……"
  if ! yt-dlp -q --progress -f ba -x --audio-format mp3 --audio-quality 0 --cookies "$JAR" \
      -o "assets/song.%(ext)s" "https://www.bilibili.com/video/BV1sb411M7be"; then
    echo "Bilibili 下载失败，改试 YouTube 官方频道……"
    yt-dlp -q --progress -x --audio-format mp3 --audio-quality 0 \
      -o "assets/song.%(ext)s" "https://www.youtube.com/watch?v=VWVtIg5cdDU"
  fi
fi

dur="$(ffprobe -v error -show_entries format=duration -of csv=p=0 assets/song.mp3)"
if awk -v d="$dur" 'BEGIN { exit !(d < 288 || d > 292) }'; then
  echo "警告：音频时长 ${dur}s，与官方版本（约 290s）不符，画面可能和音乐对不上。" >&2
  echo "      可以用 python3 play.py --offset <秒> 微调。" >&2
else
  echo "完成：assets/song.mp3（${dur%.*}s）。现在运行 python3 play.py 即可。"
fi
