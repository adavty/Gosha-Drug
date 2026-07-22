#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DEST=${1:-}

if [ -z "$DEST" ]; then
  echo "usage: $0 /path/to/new-public-export" >&2
  exit 2
fi
case "$DEST" in
  "$ROOT"|"$ROOT"/*) echo "destination must be outside the source repository" >&2; exit 2 ;;
esac
if [ -e "$DEST" ] && [ "$(find "$DEST" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
  echo "destination must not exist or must be empty: $DEST" >&2
  exit 2
fi

mkdir -p "$DEST"

copy_tracked_file() {
  path=$1
  case "$path" in
    .github/*|assets/*|data/*|docs/*|evaluation/*|migrations/*|src/*|tests/*) ;;
    scripts/run_all.sh|scripts/run_quality.sh|scripts/run_llm_evaluation.sh|scripts/check_wheel_install.sh|scripts/generate_synthetic_benchmark.py|scripts/generate_demo_gif.py|scripts/check_readme_links.py|scripts/check_public_export.py|scripts/export_public_repo.sh) ;;
    .dockerignore|.env.example|.gitignore|AI_ASSISTED_DEVELOPMENT.md|Dockerfile|LICENSE|Makefile|README.md|SECURITY.md|TECHNICAL_OVERVIEW.md|compose.yaml|pyproject.toml|uv.lock) ;;
    *) return 0 ;;
  esac
  if [ -L "$ROOT/$path" ]; then
    echo "refusing tracked symbolic link in public export: $path" >&2
    exit 1
  fi
  mkdir -p "$DEST/$(dirname "$path")"
  cp "$ROOT/$path" "$DEST/$path"
}

# Copy the current contents of explicitly allowed Git-tracked files one by one.
# Directory copies are forbidden: ignored/untracked files inside src/, tests/ or
# another allowed directory must never hitch a ride into the reviewer export.
git -C "$ROOT" ls-files | while IFS= read -r path; do
  copy_tracked_file "$path"
done

python3 "$DEST/scripts/check_public_export.py" --self-test
python3 "$DEST/scripts/check_public_export.py" "$DEST"

echo "Public export created at: $DEST"
echo "No remote or Git history was created. Review, run checks, then initialize a separate repository manually."
