#!/usr/bin/env bash
# Builds the offline demo as static files and uploads them to the Hugging Face Space $HF_SPACE.
# Needs HF_TOKEN (write). Run from anywhere in the repo: HF_SPACE=user/hope bash infra/hf-space/deploy.sh
set -euo pipefail
: "${HF_TOKEN:?}" "${HF_SPACE:?}"
cd "$(git rev-parse --show-toplevel)"
pnpm install --frozen-lockfile
rm -rf apps/web/out
HOPE_STATIC_EXPORT=1 NEXT_PUBLIC_HOPE_STATIC=1 NEXT_PUBLIC_HOPE_API_URL= pnpm --filter @hope/web build
cp infra/hf-space/README.md apps/web/out/README.md
python3 -m venv /tmp/hf-venv
/tmp/hf-venv/bin/pip install --quiet 'huggingface_hub>=0.30,<1'
/tmp/hf-venv/bin/python - <<'PY'
import os, subprocess
from huggingface_hub import HfApi
api, space = HfApi(token=os.environ["HF_TOKEN"]), os.environ["HF_SPACE"]
sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
api.create_repo(space, repo_type="space", space_sdk="static", exist_ok=True)
api.upload_folder(repo_id=space, repo_type="space", folder_path="apps/web/out", delete_patterns="*", commit_message=f"Deploy {sha}")
print(f"https://huggingface.co/spaces/{space}")
PY
