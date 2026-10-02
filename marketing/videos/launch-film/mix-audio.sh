#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
ffmpeg -y -hide_banner -loglevel error \
  -i voice/voice.wav -i audio/music.wav -i audio/sfx.wav \
  -filter_complex '[0:a]aresample=48000,highpass=f=75,pan=stereo|c0=c0|c1=c0,loudnorm=I=-17:TP=-2:LRA=6,asplit=2[v][side];[1:a]aresample=48000,equalizer=f=2000:t=q:w=0.7:g=-3[m];[m][side]sidechaincompress=threshold=0.035:ratio=3:attack=8:release=130[bed];[2:a]aresample=48000[sfx];[v][bed][sfx]amix=inputs=3:normalize=0,alimiter=limit=0.94,loudnorm=I=-16:TP=-1.5:LRA=7,aresample=48000[out]' \
  -map '[out]' -t 30 -c:a pcm_s16le audio/final-mix.wav
