#!/bin/bash
# Convert .mov demo videos to .mp4 (3x speed) and .gif for README embedding.
# Requires ffmpeg: brew install ffmpeg
set -e
cd "$(dirname "$0")"

if ! command -v ffmpeg &>/dev/null; then
  echo "ffmpeg not found. Install with: brew install ffmpeg"
  exit 1
fi

# MP4 at 3x speed
ffmpeg -i job-seeker-settings.mov -filter:v "setpts=0.333*PTS" -c:v libx264 -preset fast -crf 23 -an job-seeker-settings.mp4 -y
ffmpeg -i job-seeker-resume-view.mov -filter:v "setpts=0.333*PTS" -c:v libx264 -preset fast -crf 23 -an job-seeker-resume-view.mp4 -y
ffmpeg -i job-seeker-dashbaord-recording.mov -filter:v "setpts=0.333*PTS" -c:v libx264 -preset fast -crf 23 -an job-seeker-dashboard.mp4 -y

# GIF for README embedding (3x speed, 640px width, 8fps)
for f in job-seeker-settings job-seeker-resume-view job-seeker-dashboard; do
  [ -f "${f}.mp4" ] && ffmpeg -y -i "${f}.mp4" -vf "fps=8,scale=640:-1:flags=lanczos" -c:v gif "${f}.gif" 2>/dev/null || true
done

echo "Done. Output: *.mp4, *.gif (run from assets/)"
