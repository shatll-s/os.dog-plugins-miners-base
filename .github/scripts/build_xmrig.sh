#!/bin/bash
# Build a static, zero-donation XMRig and package the os.dog adapters.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
VERSION=${1:?usage: build_xmrig.sh VERSION}
[[ $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'Invalid XMRig version' >&2; exit 1; }
BUILD_DIR=$(mktemp -d)
trap 'rm -rf "$BUILD_DIR"' EXIT
JOBS=${JOBS:-4}
mkdir -p "$BUILD_DIR/source" "$BUILD_DIR/hwloc"
curl --fail --location --silent --show-error "https://codeload.github.com/xmrig/xmrig/tar.gz/refs/tags/v$VERSION" -o "$BUILD_DIR/xmrig.tar.gz"
curl --fail --location --silent --show-error https://download.open-mpi.org/release/hwloc/v2.12/hwloc-2.12.1.tar.gz -o "$BUILD_DIR/hwloc.tar.gz"
echo "ffa02c3a308275a9339fbe92add054fac8e9a00cb8fe8c53340094012cb7c633  $BUILD_DIR/hwloc.tar.gz" | sha256sum --check --status
tar -xzf "$BUILD_DIR/xmrig.tar.gz" -C "$BUILD_DIR/source" --strip-components=1
test "$(grep -c 'kDefaultDonateLevel = 1;' "$BUILD_DIR/source/src/donate.h")" = 1
test "$(grep -c 'kMinimumDonateLevel = 1;' "$BUILD_DIR/source/src/donate.h")" = 1
sed -i 's/kDefaultDonateLevel = 1;/kDefaultDonateLevel = 0;/; s/kMinimumDonateLevel = 1;/kMinimumDonateLevel = 0;/' "$BUILD_DIR/source/src/donate.h"
grep -q 'kDefaultDonateLevel = 0;' "$BUILD_DIR/source/src/donate.h"
grep -q 'kMinimumDonateLevel = 0;' "$BUILD_DIR/source/src/donate.h"
tar -xzf "$BUILD_DIR/hwloc.tar.gz" -C "$BUILD_DIR/hwloc" --strip-components=1
cd "$BUILD_DIR/hwloc"
./configure --prefix="$BUILD_DIR/deps" --disable-shared --enable-static --disable-io --disable-libudev --disable-libxml2 --disable-libnuma
make -j"$JOBS"
make install
MULTIARCH=$(gcc -print-multiarch)
cmake -S "$BUILD_DIR/source" -B "$BUILD_DIR/build" -DBUILD_STATIC=ON -DXMRIG_DEPS="$BUILD_DIR/deps" -DUV_LIBRARY="/usr/lib/$MULTIARCH/libuv.a" -DOPENSSL_INCLUDE_DIR=/usr/include -DOPENSSL_CRYPTO_LIBRARY="/usr/lib/$MULTIARCH/libcrypto.a" -DOPENSSL_SSL_LIBRARY="/usr/lib/$MULTIARCH/libssl.a" -DWITH_OPENCL=OFF -DWITH_CUDA=OFF -DWITH_KAWPOW=OFF
cmake --build "$BUILD_DIR/build" -j"$JOBS"
"$BUILD_DIR/build/xmrig" --version | head -1 | grep -Fx "XMRig $VERSION"
"$BUILD_DIR/build/xmrig" --dry-run --no-color --no-cpu -o example.invalid:3333 -u test | grep -Eq 'DONATE +0%'
install -m755 "$BUILD_DIR/build/xmrig" "$ROOT/miners/xmrig/xmrig"
cp "$BUILD_DIR/source/LICENSE" "$ROOT/miners/xmrig/LICENSE"
cd "$ROOT/miners/xmrig"
md5sum ./miner ./stats ./profile.sh ./xmrig ./LICENSE > "$BUILD_DIR/files.md5"
cp "$BUILD_DIR/files.md5" files.md5
trap 'rm -rf "$BUILD_DIR"; rm -f "$ROOT/miners/xmrig/files.md5"' EXIT
tar -chzf "$ROOT/releases/xmrig-$VERSION.tar.gz" --transform 's,^,./,' miner stats profile.sh xmrig LICENSE files.md5
python3 - "$ROOT/manifest.json" "$VERSION" <<'PY'
import json, sys
from pathlib import Path
path=Path(sys.argv[1]); version=sys.argv[2]; text=path.read_text(); manifest=json.loads(text)
entry=next(x for x in manifest['miners'] if x['id']=='xmrig')
start=text.index('      "id": "xmrig"'); end=text.index('\n    },',start); block=text[start:end]
block=block.replace('"latest": "'+entry['latest']+'"', '"latest": "'+version+'"', 1)
if version not in entry['versions']:
 url='https://raw.githubusercontent.com/shatll-s/os.dog-plugins-miners-base/main/releases/xmrig-'+version+'.tar.gz'
 block=block.replace('"versions": {', '"versions": {\n        "'+version+'": "'+url+'",', 1)
path.write_text(text[:start]+block+text[end:])
PY
