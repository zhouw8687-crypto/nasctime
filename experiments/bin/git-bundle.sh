#!/usr/bin/env bash
# 生成异地备份 bundle（含全部历史），默认输出到仓库外一层
# 用法：experiments/bin/git-bundle.sh [输出路径]
# 恢复：git clone <bundle> nascTime-restored
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="${1:-$ROOT/../nasctime-repo-$(date +%Y%m%d-%H%M).bundle}"

git -C "$ROOT" bundle create "$OUT" --all >/dev/null
SIZE="$(du -h "$OUT" | cut -f1)"
echo "已生成: $OUT ($SIZE)"
echo "异地恢复: git clone \"$OUT\" nascTime-restored"
