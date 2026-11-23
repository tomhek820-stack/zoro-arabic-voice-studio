#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

REPO_NAME="zoro-arabic-voice-studio"
OWNER="${GITHUB_OWNER:-tomhek820-stack}"

echo "== فحص المتطلبات =="
command -v git >/dev/null || { echo "ثبّت git: pkg install git"; exit 1; }
command -v gh >/dev/null || { echo "ثبّت gh: pkg install gh"; exit 1; }
gh auth status >/dev/null || { echo "سجّل الدخول أولاً: gh auth login"; exit 1; }

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "== فحص الملفات الأساسية =="
test -s .github/workflows/voice.yml
test -s scripts/generate.py
test -s scripts/story.txt
python - <<'PY'
from pathlib import Path
import ast
ast.parse(Path("scripts/generate.py").read_text(encoding="utf-8"))
print("Python syntax: OK")
PY

git init -b main
if ! git config user.name >/dev/null; then
  git config user.name "$OWNER"
fi
if ! git config user.email >/dev/null; then
  git config user.email "$(gh api user --jq '.login')@users.noreply.github.com"
fi
git add .
git commit -m "Initial Arabic voice generation project"

if gh repo view "$OWNER/$REPO_NAME" >/dev/null 2>&1; then
  echo "المستودع موجود مسبقاً: $OWNER/$REPO_NAME"
  git remote remove origin 2>/dev/null || true
  git remote add origin "https://github.com/$OWNER/$REPO_NAME.git"
  git push -u origin main
else
  gh repo create "$OWNER/$REPO_NAME" --public --source=. --remote=origin --push \
    --description "Free Arabic narration generation with Chatterbox Multilingual V3"
fi

echo
echo "تم رفع المشروع."
echo "افتح: https://github.com/$OWNER/$REPO_NAME/actions"
echo "شغّل Generate Arabic Narration ثم نزّل ملف Artifact."
