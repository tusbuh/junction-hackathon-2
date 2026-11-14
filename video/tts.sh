#!/bin/zsh
# narration.json -> /tmp/ppvid/audio/<id>.wav (macOS say), prints durations
set -e
OUT=${1:-/tmp/ppvid/audio}; mkdir -p $OUT
python3 - "$OUT" <<'PY'
import json, subprocess, sys
out = sys.argv[1]
d = json.load(open('narration.json'))
for s in d['scenes']:
    aiff = f"{out}/{s['id']}.aiff"; wav = f"{out}/{s['id']}.wav"
    subprocess.run(['say', '-v', d['voice'], '-r', str(d['rate']), '-o', aiff, s['text']], check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', aiff, '-ar', '48000', '-ac', '2', wav], check=True)
    dur = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', wav]).decode())
    print(f"{s['id']} {dur:.2f}")
PY
