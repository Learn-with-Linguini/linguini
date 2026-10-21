#!/usr/bin/env bash
# Build the launch film end to end: footage, tracking, overlay, score, mix.
# Needs Python 3 (requirements.txt), Node with Playwright's Chromium, and ffmpeg.
# Usage: ./render.sh            (writes out/linguini-launch-master.mp4 and the web cuts)
set -euo pipefail
cd "$(dirname "$0")"
PORT=${PORT:-8093}

python3 edit.py                       # timeline.json from the edit list
python3 fetch.py                      # Mixkit clips and piano samples into cache/
python3 plate.py cache/clips timeline.json cache/plate.mp4 boxes.json
python3 score.py cache/piano audio cache/score.wav timeline.json audio/piano-notes.json
ffmpeg -v error -y -i cache/score.wav -c:a flac -sample_fmt s16 audio/score.flac

python3 -m http.server "$PORT" >/dev/null 2>&1 &
SERVER=$!
trap 'kill $SERVER' EXIT
sleep 1
rm -rf cache/overlay
node overlay.mjs "http://localhost:$PORT" cache/overlay

bash composite.sh cache/plate.mp4 cache/overlay audio/score.flac out/linguini-launch-master.mp4 17
ffmpeg -v error -y -i out/linguini-launch-master.mp4 -c:v libx264 -preset slow -crf 25 -tune film \
  -pix_fmt yuv420p -movflags +faststart -c:a copy out/linguini-launch.mp4
ffmpeg -v error -y -i out/linguini-launch-master.mp4 -vf scale=1280:720:flags=lanczos -c:v libx264 -preset slow \
  -crf 24 -tune film -pix_fmt yuv420p -movflags +faststart -c:a aac -b:a 160k out/linguini-launch-720p.mp4
ffmpeg -v error -y -ss 26.2 -i out/linguini-launch-master.mp4 -frames:v 1 -q:v 2 out/poster.jpg
ls -la out
