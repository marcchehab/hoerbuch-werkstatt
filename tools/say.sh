#!/bin/sh
# Namen auf Mandarin vorsprechen (Microsoft neural voice via edge-tts, braucht Internet).
# Nutzung: tools/say.sh 叶哲泰 [weitere Zeichen...]
# Stimme ändern: VOICE=zh-CN-YunxiNeural tools/say.sh 叶哲泰   (Liste: edge-tts --list-voices | grep zh-CN)
# Clips landen in buecher/.cache/namen/<text>.mp3 und werden wiederverwendet.
set -e
VOICE="${VOICE:-zh-CN-XiaoxiaoNeural}"
dir="$(dirname "$0")/../buecher/.cache/namen"
mkdir -p "$dir"
for t in "$@"; do
  f="$dir/$t.mp3"
  [ -f "$f" ] || edge-tts -v "$VOICE" -t "$t" --write-media "$f" >/dev/null 2>&1
  ffplay -nodisp -autoexit -loglevel error "$f"
done
