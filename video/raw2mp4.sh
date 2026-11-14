#!/bin/zsh
# screencast frames (variable timing) -> constant 30 fps near-lossless intermediate, then delete the frames
for id in "$@"; do
  d=/tmp/ppvid/rec/$id
  [[ -f $d/list.txt ]] || continue
  ffmpeg -v error -y -f concat -safe 0 -i $d/list.txt -vf fps=30,scale=1920:960,format=yuv420p -c:v libx264 -preset veryfast -crf 12 /tmp/ppvid/rec/$id.mp4 && rm -rf $d && echo "$id -> $(du -h /tmp/ppvid/rec/$id.mp4 | cut -f1)"
done
