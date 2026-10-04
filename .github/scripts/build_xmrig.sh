#!/bin/bash
# Rebuild the shipped XMRig from the accompanying modified source archive.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
VERSION=6.26.0
BUILD_DIR=$(mktemp -d)
trap 'rm -rf "$BUILD_DIR"' EXIT
JOBS=${JOBS:-6}

mkdir -p "$BUILD_DIR/source" "$BUILD_DIR/hwloc"
tar -xzf "$ROOT/releases/xmrig-$VERSION-source.tar.gz" -C "$BUILD_DIR/source" --strip-components=1
grep -q 'kDefaultDonateLevel = 0;' "$BUILD_DIR/source/src/donate.h"
grep -q 'kMinimumDonateLevel = 0;' "$BUILD_DIR/source/src/donate.h"
tar -xzf "$BUILD_DIR/source/vendor/hwloc-2.12.1.tar.gz" -C "$BUILD_DIR/hwloc" --strip-components=1
cd "$BUILD_DIR/hwloc"
./configure --prefix="$BUILD_DIR/deps" --disable-shared --enable-static --disable-io --disable-libudev --disable-libxml2 --disable-libnuma
make -j"$JOBS"
make install

MULTIARCH=$(gcc -print-multiarch)
cmake -S "$BUILD_DIR/source" -B "$BUILD_DIR/build" \
  -DBUILD_STATIC=ON -DXMRIG_DEPS="$BUILD_DIR/deps" \
  -DUV_LIBRARY="/usr/lib/$MULTIARCH/libuv.a" \
  -DOPENSSL_INCLUDE_DIR=/usr/include \
  -DOPENSSL_CRYPTO_LIBRARY="/usr/lib/$MULTIARCH/libcrypto.a" \
  -DOPENSSL_SSL_LIBRARY="/usr/lib/$MULTIARCH/libssl.a" \
  -DWITH_OPENCL=OFF -DWITH_CUDA=OFF -DWITH_KAWPOW=OFF
cmake --build "$BUILD_DIR/build" -j"$JOBS"
install -m755 "$BUILD_DIR/build/xmrig" "$ROOT/miners/xmrig/xmrig"
cp "$BUILD_DIR/source/LICENSE" "$ROOT/miners/xmrig/"
cd "$ROOT/miners/xmrig"
md5sum ./miner ./stats ./xmrig ./LICENSE > files.md5
tar -czf "$ROOT/releases/xmrig-$VERSION.tar.gz" --transform 's,^,./,' miner stats xmrig LICENSE files.md5
rm files.md5
