#!/usr/bin/env bash
# Copies what the Hugging Face Space needs (the web app and its workspace) into OUTDIR.
set -euo pipefail
out=${1:?usage: assemble.sh OUTDIR}
cd "$(git rev-parse --show-toplevel)"
mkdir -p "$out"
git ls-files -z package.json pnpm-lock.yaml pnpm-workspace.yaml LICENSE apps/web packages/schemas/ts contracts \
  | xargs -0 cp --parents -t "$out"
cp infra/hf-space/Dockerfile infra/hf-space/README.md "$out/"
