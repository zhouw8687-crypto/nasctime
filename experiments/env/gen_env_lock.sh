#!/usr/bin/env bash
# 生成 experiments/env/env.lock.yaml —— 环境版本锁定
# 用法：experiments/env/gen_env_lock.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
OUT="experiments/env/env.lock.yaml"
mkdir -p "$(dirname "$OUT")"

sha() { if [ -f "$1" ]; then sha256sum "$1" | awk '{print $1}'; else echo "missing"; fi; }

INETHEX="$(sed -n 's/^#define INET_VERSION[[:space:]]*0x\(....\)/\1/p' inet/src/inet/common/INETDefs.h 2>/dev/null | head -1)"
INETVER="$(printf '%d.%d' "$((16#${INETHEX:0:2}))" "$((16#${INETHEX:2:2}))" 2>/dev/null || echo "${INETHEX:-unknown}")"
OMNETVER="$(head -1 omnetpp-6.4.0/Version 2>/dev/null)"
GCC="$(gcc --version | head -1)"
PY="$(/media/a100/data/zbw/conda-envs/nasctime/bin/python --version 2>&1)"
SIMU_FILES="$(find Simu5G/src -type f 2>/dev/null | wc -l)"
SIMU_NEWEST="$(find Simu5G/src -type f \( -name '*.cc' -o -name '*.h' -o -name '*.ned' -o -name '*.msg' \) -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)"

{
  echo "# 环境版本锁定（自动生成，勿手改）"
  echo "# 生成器：experiments/env/gen_env_lock.sh"
  echo "generated_at: \"$(date -u '+%Y-%m-%dT%H:%M:%SZ')\""
  echo "host: \"$(hostname)\""
  echo "kernel: \"$(uname -r)\""
  echo "os: \"$(. /etc/os-release 2>/dev/null && echo "${PRETTY_NAME}" || uname -s)\""
  echo "cpu_cores: $(nproc)"
  echo "memory_gb: $(awk '/MemTotal/{printf "%d", $2/1024/1024}' /proc/meminfo)"
  echo "disk_root: \"/media/a100/data\""
  echo ""
  echo "toolchain:"
  echo "  gcc: \"${GCC}\""
  echo "  python: \"${PY}\""
  echo "  conda_env: \"/media/a100/data/zbw/conda-envs/nasctime\""
  echo "  git: \"$(git --version)\""
  echo ""
  echo "components:"
  echo "  omnetpp: \"${OMNETVER:-unknown}\""
  echo "  inet: \"${INETVER:-unknown}\"   # INETDefs.h INET_VERSION"
  echo "  simu5g: \"fork nasctime-v1.0 (based on 1.5.0)\""
  echo "  simu5g_src_files: ${SIMU_FILES}"
  echo "  simu5g_newest_src: \"${SIMU_NEWEST}\""
  echo "  simu5g_fork_patch: \"experiments/env/Simu5G-fork.patch\""
  echo ""
  echo "# 归档文件 sha256：用于确认恢复用的是同一份压缩包"
  echo "archives:"
  for f in omnetpp-6.4.0-linux-x86_64.tgz inet-4.6.0.zip Simu5G-1.5.0.zip Simu5G-fork.zip nascTime.zip 2604.04616v2.pdf; do
    printf '  "%s": "%s"\n' "$f" "$(sha "$f")"
  done
  echo ""
  echo "# 关键语义约束（源码复核得出，勿随意改动）"
  echo "invariants:"
  echo "  - \"Simu5G TTI = 2^-numerologyIndex / 1000 s（Binder.h:229）；默认 numerologyIndex=0 => 1ms\""
  echo "  - \"TTI 在 INITSTAGE_SIMU5G_TTI_SETUP 由 numerology 覆盖（LteMacEnb.cc:173 / LteMacUe.cc:158）\""
  echo "  - \"INET 4.6 无 CQF(802.1Qch)、无动态 BMCA\""
  echo "  - \"nascTime TsnAf::applyGateControlList() 只记录日志，不编程 TSN 设备\""
  echo "  - \"results/ 与 *.vec 永不入库；单 run 白名单录制目标 < 30MB\""
} > "$OUT"

echo "written: $OUT"
