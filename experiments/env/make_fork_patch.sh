#!/usr/bin/env bash
# 生成 Simu5G 相对 vanilla 1.5.0 的补丁存档 —— 用于误覆盖后的回滚
# 用法：experiments/env/make_fork_patch.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
OUT="experiments/env/Simu5G-fork.patch"
mkdir -p "$(dirname "$OUT")"

TMP="$(mktemp)"
diff -ruN -x out -x results -x '*.o' -x '*.so' -x '*.so.*' -x '*.a' \
     Simu5G-vanilla-1.5.0 Simu5G > "$TMP" 2>/dev/null || true

{
  echo "# Simu5G fork (nasctime-v1.0) vs vanilla 1.5.0 的差异存档"
  echo "# 生成时间: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "# 生成命令: experiments/env/make_fork_patch.sh"
  echo "#"
  echo "# 回滚方式（在仓库根目录执行）："
  echo "#   rm -rf Simu5G && cp -a Simu5G-vanilla-1.5.0 Simu5G"
  echo "#   patch -p0 < experiments/env/Simu5G-fork.patch"
  echo "# 说明：差异仅涉及已有文件修改，无新增文件；因此 patch 必然干净可逆。"
  echo ""
  cat "$TMP"
} > "$OUT"

rm -f "$TMP"
echo "written: $OUT"
wc -l "$OUT"
grep -c '^diff ' "$OUT" || true
