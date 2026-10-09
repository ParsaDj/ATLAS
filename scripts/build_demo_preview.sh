#!/bin/sh
set -eu

input=${1:-apps/dashboard/demo-artifacts/atlas-incident-investigation.webm}
output=${2:-docs/assets/atlas-incident-investigation.gif}

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is required to build the README preview" >&2
  exit 1
fi

mkdir -p "$(dirname "$output")"
ffmpeg -y -i "$input" -filter_complex \
  "fps=8,scale=960:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=256:stats_mode=diff[p];[s1][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle" \
  "$output"
