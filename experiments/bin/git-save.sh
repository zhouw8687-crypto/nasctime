#!/usr/bin/env bash
# 一键保存：把当前改动提交到 git
# 用法：
#   experiments/bin/git-save.sh "feat: 说明"
#   experiments/bin/git-save.sh            # 不写说明则用时间戳
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "错误：$ROOT 不是 git 仓库" >&2
  exit 1
fi

MSG="${1:-chore: 自动保存 $(date '+%Y-%m-%d %H:%M')}"

git add -A

if git diff --cached --quiet; then
  echo "没有改动，跳过提交。"
  exit 0
fi

COUNT="$(git diff --cached --name-only | wc -l)"
git commit -q -m "$MSG"
echo "已提交 ${COUNT} 个文件"
git --no-pager log -1 --stat --oneline | head -20
