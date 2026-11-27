#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK="$ROOT/work"
DIST="$ROOT/dist"
if [[ -n ${KSU_EXPECTED_SIZE+x} || -n ${KSU_EXPECTED_HASH+x} ]]; then
  echo 'Custom manager signature overrides are not supported' >&2; exit 1
fi
mkdir -p "$WORK" "$DIST"
exec 8>"$WORK/build.lock"
flock -n 8
exec > >(tee "$DIST/build.log") 2>&1
python3 "$ROOT/scripts/inputs.py" ${BUILD_DATE:+--date "$BUILD_DATE"} --output "$WORK/input"
readarray -t values < <(python3 -c 'import json,sys;x=json.load(open(sys.argv[1]));print(x["kernel_commit"]);print(x["boot"]["sha256"])' "$WORK/input/inputs.json")
KERNEL_REV=${values[0]}
BOOT_SHA=${values[1]}
fetch() {
  local dir=$1 url=$2 rev=$3
  test ! -e "$dir" || { echo "Refusing existing source: $dir" >&2; exit 1; }
  git init -q "$dir"
  git -C "$dir" remote add origin "$url"
  git -C "$dir" fetch --depth=1 origin "$rev"
  git -C "$dir" checkout --detach FETCH_HEAD
  test "$(git -C "$dir" rev-parse HEAD)" = "$rev"
}
fetch "$WORK/kernel" https://github.com/LineageOS/android_kernel_oneplus_sm8250.git "$KERNEL_REV"
fetch "$WORK/BakaSU" https://github.com/Baka-SU/BakaSU.git cac1e79355ef451539f5c5ba9dc2bda1c64069de
git -C "$WORK/BakaSU" fetch --unshallow
test "$(git -C "$WORK/BakaSU" rev-parse --is-shallow-repository)" = false
fetch "$WORK/mkbootimg" https://android.googlesource.com/platform/system/tools/mkbootimg d2bb0af5ba6d3198a3e99529c97eda1be0b5a093
fetch "$WORK/avb" https://android.googlesource.com/platform/external/avb 761178607206f4cb2af79ed9eec52d8cbd814adb
# The prebuilt checkout is sparse, but pinned to the same source tree as the tested compiler.
if [[ ! -e "$WORK/clang" ]]; then
  git init -q "$WORK/clang"
  git -C "$WORK/clang" remote add origin https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86
  git -C "$WORK/clang" sparse-checkout init --cone
  git -C "$WORK/clang" sparse-checkout set clang-r596125
  git -C "$WORK/clang" fetch --depth=1 --filter=blob:none origin 383d35d98a3e1635d2e3a88d866b125d7d20a0c1
  git -C "$WORK/clang" checkout --detach FETCH_HEAD
fi
test "$(git -C "$WORK/clang" rev-parse HEAD)" = 383d35d98a3e1635d2e3a88d866b125d7d20a0c1
git -C "$WORK/clang" diff --quiet HEAD -- clang-r596125
test -z "$(git -C "$WORK/clang" ls-files --others --exclude-standard -- clang-r596125)"
export PATH="$WORK/clang/clang-r596125/bin:$PATH"
clang --version | grep -F 'clang version 22.0.2'
python3 "$WORK/mkbootimg/unpack_bootimg.py" --boot_img "$WORK/input/boot.img" --out "$WORK/unpacked"
python3 - "$WORK/unpacked/kernel" "$KERNEL_REV" "$WORK" <<'PY'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1]); data = p.read_bytes(); commit = sys.argv[2]
versions = re.findall(rb'Linux version 4\.19\.325-cip[0-9]+-st[0-9]+-perf-g[0-9a-f]{12} [^\x00\n]{0,1000}', data)
if len(versions) != 1: raise SystemExit('unsupported or ambiguous kernel release')
line = versions[0].decode(); release = line.split()[2]
if not release.endswith('-g' + commit[:12]): raise SystemExit('manifest/boot commit mismatch')
if b'based on r596125' not in versions[0] or b'clang version 22.0.2' not in versions[0]: raise SystemExit('unsupported stock toolchain')
(pathlib.Path(sys.argv[3])/'release').write_text(release+'\n')
PY
"$WORK/kernel/scripts/extract-ikconfig" "$WORK/unpacked/kernel" > "$WORK/stock.config"
git -C "$WORK/kernel" apply --check "$ROOT/patches/kernel-integration.patch"
git -C "$WORK/kernel" apply "$ROOT/patches/kernel-integration.patch"
ln -s "$WORK/BakaSU/kernel" "$WORK/kernel/drivers/kernelsu"
cd "$WORK/kernel"
printf '%s\n' "-g${KERNEL_REV:0:12}" > .scmversion
mkdir out
cp "$WORK/stock.config" out/.config
scripts/config --file out/.config --enable KSU --enable KSU_MANUAL_HOOK
export KBUILD_BUILD_USER=builder KBUILD_BUILD_HOST=github-actions KBUILD_BUILD_VERSION=1
export KBUILD_BUILD_TIMESTAMP="$(date -u -d "${BUILD_DATE:-$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["date"])' "$WORK/input/inputs.json")}" '+%a %b %d 00:00:00 UTC %Y')"
args=(O=out ARCH=arm64 LLVM=1 LLVM_IAS=1 CROSS_COMPILE=aarch64-linux-gnu- CROSS_COMPILE_ARM32=arm-linux-gnueabi- CROSS_COMPILE_COMPAT=arm-linux-gnueabi- HOSTCC=gcc HOSTCXX=g++ HOSTLDFLAGS=)
make "${args[@]}" olddefconfig
for option in KSU KSU_MANUAL_HOOK KSU_MANUAL_HOOK_AUTO_SETUID_HOOK KSU_MANUAL_HOOK_AUTO_INITRC_HOOK KSU_MANUAL_HOOK_AUTO_INPUT_HOOK MODULES MODVERSIONS LTO_CLANG CFI_CLANG; do
  grep -qx "CONFIG_${option}=y" out/.config || { echo "Missing CONFIG_$option" >&2; exit 1; }
done
if grep -Eq '^CONFIG_KSU_(SUSFS|KPROBES_HOOK|SYSCALL_TABLE_HOOK)=y$' out/.config; then echo 'Unsupported hook/config' >&2; exit 1; fi
python3 "$ROOT/scripts/check-config.py" "$WORK/stock.config" out/.config
make "${args[@]}" -j"${BUILD_JOBS:-4}" Image
test "$(cat out/include/config/kernel.release)" = "$(cat "$WORK/release")"
cp out/arch/arm64/boot/Image "$DIST/Image"
cp out/.config "$DIST/kernel.config"
cp "$WORK/stock.config" "$DIST/stock.config"
cp "$WORK/input/inputs.json" "$DIST/inputs.json"
cp "$ROOT/patches/kernel-integration.patch" "$DIST/kernel-integration.patch"
printf '{"stock_boot_sha256":"%s","partition_size":100663296}\n' "$BOOT_SHA" > "$WORK/input/build-lock.json"
python3 "$ROOT/scripts/repack.py" "$WORK/input" "$WORK" "$DIST"
mv "$DIST/boot-ksunext.img" "$DIST/boot-bakasu.img"
python3 "$ROOT/scripts/report.py" "$WORK" "$DIST"
(cd "$DIST" && sha256sum boot-bakasu.img Image kernel.config stock.config inputs.json kernel-integration.patch verification.json report.json > SHA256SUMS)
