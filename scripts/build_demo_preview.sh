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
  "fps=5,scale=720:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=64[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4" \
  "$output"
