#!/bin/bash
# Convert .mov demo videos to .mp4 at 3x speed for README.
# Requires ffmpeg: brew install ffmpeg
set -e
cd "$(dirname "$0")"

ffmpeg -i job-seeker-settings.mov -filter:v "setpts=0.333*PTS" -c:v libx264 -preset fast -crf 23 -an job-seeker-settings.mp4 -y
ffmpeg -i job-seeker-resume-view.mov -filter:v "setpts=0.333*PTS" -c:v libx264 -preset fast -crf 23 -an job-seeker-resume-view.mp4 -y
ffmpeg -i job-seeker-dashbaord-recording.mov -filter:v "setpts=0.333*PTS" -c:v libx264 -preset fast -crf 23 -an job-seeker-dashboard.mp4 -y

echo "Done. Output: job-seeker-settings.mp4, job-seeker-resume-view.mp4, job-seeker-dashboard.mp4"
