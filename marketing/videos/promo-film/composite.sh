#!/usr/bin/env bash
# Overlay frames on the plate, add film grain, master the score, mux.
# Every overlay frame must be RGBA: if the PNG format switches mid-sequence, ffmpeg
# rebuilds the graph and drops frames (overlay.js keeps the end card below full opacity).
# Usage: composite.sh <plate.mp4> <overlay-dir> <score.wav> <out.mp4> [crf]
set -euo pipefail
PLATE=$1 OV=$2 SCORE=$3 OUT=$4 CRF=${5:-18}
ffmpeg -v error -y \
  -i "$PLATE" -framerate 30 -i "$OV/%05d.png" -i "$SCORE" \
  -filter_complex "[0:v][1:v]overlay=format=auto,noise=c0s=7:c0f=t+u:c1s=2:c2s=2,format=yuv420p[v];[2:a]volume=6.2dB,alimiter=limit=0.84:level=false:attack=3:release=60,aresample=48000[a]" \
  -map "[v]" -map "[a]" -c:v libx264 -preset slow -crf "$CRF" -profile:v high -tune film -movflags +faststart \
  -c:a aac -b:a 256k -shortest "$OUT"
ffmpeg -hide_banner -i "$OUT" -af ebur128=peak=true -f null - 2>&1 | grep -E "^\s+(I|True peak|Peak):" | head -3
