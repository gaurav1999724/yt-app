#!/usr/bin/env bash
# Render build: Python deps + static ffmpeg/ffprobe on PATH
set -o errexit

pip install -r pipeline/requirements.txt

mkdir -p "$HOME/bin"
if [ ! -x "$HOME/bin/ffmpeg" ]; then
  echo "Installing static ffmpeg..."
  cd /tmp
  curl -sL https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz -o ffmpeg.tar.xz
  tar -xf ffmpeg.tar.xz
  cp ffmpeg-*-amd64-static/ffmpeg ffmpeg-*-amd64-static/ffprobe "$HOME/bin/"
  chmod +x "$HOME/bin/ffmpeg" "$HOME/bin/ffprobe"
fi

"$HOME/bin/ffmpeg" -version | head -n 1
echo "Build OK"
