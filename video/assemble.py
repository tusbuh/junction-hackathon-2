#!/usr/bin/env python3
"""Assemble the PINPOINT demo: per-scene clips (screencast frames + caption band + narration) -> one H.264/AAC MP4."""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REC, AUD, CARDS, WORK = '/tmp/ppvid/rec', '/tmp/ppvid/audio', '/tmp/ppvid/cards', '/tmp/ppvid/clips'
OUT = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else '~/junction-hackathon-2/shots_tmp/submission/video.mp4')
os.makedirs(WORK, exist_ok=True)
cfg = json.load(open(f'{HERE}/scenes.json'))
lead = cfg['lead']
durs = dict(l.split() for l in open(f'{AUD}/durations.txt').read().split('\n') if l.strip())
X264 = ['-c:v', 'libx264', '-preset', 'slow', '-crf', '20', '-pix_fmt', 'yuv420p', '-r', '30', '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-ac', '2']

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: print(' '.join(cmd)); print(r.stderr[-3000:]); sys.exit(1)

clips = []
for s in cfg['scenes']:
    sid = s['id']; T = max(s['minT'], lead + float(durs[sid]) + 1.0)
    out = f'{WORK}/{sid}.mp4'
    audio = ['-i', f'{AUD}/{sid}.wav']
    afilt = f'[1:a]adelay={int(lead*1000)}|{int(lead*1000)},loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,apad,atrim=0:{T:.3f}[a]'
    if 'card' in s:
        fade = f'fade=t=in:st=0:d=0.6' if s['card'] == 'title' else 'fade=t=in:st=0:d=0.4,fade=t=out:st=%.2f:d=1.0' % (T - 1.0)
        run(['ffmpeg', '-v', 'error', '-y', '-loop', '1', '-framerate', '30', '-t', f'{T:.3f}', '-i', f'{CARDS}/{s["card"]}.png', *audio,
             '-filter_complex', f'[0:v]scale=1920:1080,format=yuv420p,{fade}[v];{afilt}', '-map', '[v]', '-map', '[a]', '-t', f'{T:.3f}', *X264, out])
    else:
        caps = s.get('captions', [])
        inputs = ['-i', f'{REC}/{sid}.mp4', *audio]
        for i in range(len(caps)): inputs += ['-loop', '1', '-framerate', '30', '-t', f'{T:.3f}', '-i', f'{CARDS}/{sid}_c{i}.png']
        # 30 fps constant, trim to T, stack on a 120 px caption band, overlay each caption from its start time
        fc = f'[0:v]fps=30,trim=0:{T:.3f},setpts=PTS-STARTPTS,scale=1920:960,pad=1920:1080:0:0:color=0x06090f[v0]'
        last = 'v0'
        for i, (t, _) in enumerate(caps):
            t1 = caps[i + 1][0] if i + 1 < len(caps) else T + 1
            fc += f';[{2+i}:v]format=rgba,fade=t=in:st={t:.2f}:d=0.25:alpha=1[c{i}];[{last}][c{i}]overlay=0:960:enable=\'between(t,{t:.2f},{t1:.2f})\'[v{i+1}]'
            last = f'v{i+1}'
        fc += f';[{last}]format=yuv420p[v];{afilt}'
        run(['ffmpeg', '-v', 'error', '-y', *inputs, '-filter_complex', fc, '-map', '[v]', '-map', '[a]', '-t', f'{T:.3f}', *X264, out])
    clips.append(out); print(sid, f'{T:.2f}s')

lst = f'{WORK}/concat.txt'
open(lst, 'w').write(''.join(f"file '{c}'\n" for c in clips))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', '-movflags', '+faststart', OUT])
d = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration,size', '-of', 'json', OUT]).decode()
print(OUT, d)
