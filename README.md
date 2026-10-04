# os.dog miner plugins

## Structure

```
/
├── manifest.json        # package manifest with miners array
├── miners/
│   └── <miner_id>/      # source files per miner
│       ├── miner         # launch script (required)
│       ├── stats         # stats collection script (required)
│       └── <binary>      # miner binary (optional, may be large)
└── releases/
    └── <miner_id>-<version>.tar.gz  # packaged archives
```

## Adding a new miner

### 1. Create miner directory

```bash
mkdir miners/<miner_id>
```

### 2. Create `miner` script

Executable bash script that launches the miner. Receives the **profile path** as the first argument.

```bash
#!/bin/bash
. /dog/colors
cd `dirname $0`

PROFILE="$1"
[[ -z "$PROFILE" || ! -f "$PROFILE" ]] && echo -e "${RED}Usage: $0 <profile.json>${WHITE}" && exit 1

# Read fields from profile
ALGO=$(jq -r '.algo // empty' "$PROFILE")
PASS=$(jq -r '.pass // empty' "$PROFILE")
POOL=$(jq -r '.pool // empty' "$PROFILE")
TEMPLATE=$(jq -r '.template // empty' "$PROFILE")
API_PORT=$(jq -r '.api_port // empty' "$PROFILE")
ADDITION=$(jq -r '.addition // empty' "$PROFILE")

LOG="/dog/log/<miner_id>.log"

# Build and run command
batch="./<binary>"
# ... add miner-specific flags ...
batch+=" $ADDITION"

echo -e "${GREEN}> Starting <miner_name>: $batch${WHITE}"
unbuffer $batch 2>&1 | tee $LOG
```

### 3. Create `stats` script

Executable bash script that queries the miner's API and outputs a single-line JSON. Receives the **profile path** as the first argument.

```bash
#!/bin/bash
cd `dirname $0`

PROFILE="$1"
[[ -z "$PROFILE" || ! -f "$PROFILE" ]] && echo "Usage: $0 <profile.json>" && exit 1

API_PORT=$(jq -r '.api_port // empty' "$PROFILE")
[[ -z "$API_PORT" ]] && exit 1

# Query miner API, parse response, output JSON
```

Required output JSON format:

```json
{
  "miner": "<miner_id>",
  "algo": "ethash",
  "online": 1708300000,
  "ver": "1.0.0",
  "total_hr": "150000000.00",
  "total_share": "42.00",
  "total_badshare": "0.00",
  "temp": [55, 60, 58],
  "fan": [70, 75, 72],
  "hr": [50000000, 50000000, 50000000],
  "share": [14, 14, 14],
  "badshare": [0, 0, 0],
  "busid": {"0": "01", "1": "02", "2": "03"}
}
```

Fields: `miner` is required, the rest are optional (include what the miner API provides).

### 4. Build the archive

From the miner's directory:

```bash
cd miners/<miner_id>
rm -f files.md5 miner.tar.gz
find . -type f ! -name "files.md5" -exec md5sum {} \; > files.md5
tar -zcf miner.tar.gz *
rm -f files.md5
mv miner.tar.gz ../../releases/<miner_id>-<version>.tar.gz
```

The archive will contain `miner`, `stats`, the binary, and `files.md5` (checksums for integrity verification).

### 5. Register in manifest.json

Add an entry to the `miners` array:

```json
{
  "package": "os.dog-plugins-miners-base",
  "description": "Base miners",
  "label": "Short label for display in system",
  "miners": [
    {
      "id": "<miner_id>",
      "name": "Display Name",
      "latest": "<version>",
      "algos": [
        { "g": "<system_algo_name>", "i": "<miner_algo_param>" }
      ],
      "versions": {
        "<version>": "https://raw.githubusercontent.com/.../releases/<miner_id>-<version>.tar.gz"
      }
    }
  ]
}
```

Manifest fields:
- `algos` — list of supported algorithms for the **latest** version. `g` is the algorithm name in the os.dog system, `i` is the parameter passed to this specific miner implementation
- `versions` — map of version → archive URL (latest version first)

The same manifest structure is used across all plugin packages (`os.dog-plugins-miners-base`, `os.dog-plugins-miners-extra`, etc.) — only `package` and `miners` content differ.

## Release maintenance

OneZeroMiner and BzMiner have scheduled auto-builds, like SRBMiner. Every
10 minutes they check the latest stable upstream release, verify its SHA-256,
package the Linux binary with the os.dog scripts and `files.md5`, reconcile
the supported algorithms, and commit the result. They retain the three most
recent version URLs. The three workflows share a concurrency group to avoid
simultaneous manifest updates.

Each workflow can also be run manually with a version and `dry_run=true`.
A dry run uploads the package and manifest as a GitHub Actions artifact and
does not push. Specifying a version forces a rebuild, even when it is current.

Algorithm reconciliation preserves existing `g` mappings for parameters still
supported, adds new parameters and removes unsupported ones. BzMiner uses
`--list-algos` JSON with aliases deduplicated. OneZeroMiner uses its binary's
help and the active README table: 1.7.8's help omits the supported `pearlhash`.
SRBMiner includes its CPU algorithms as well as GPU algorithms.

XMRig 6.26.0 is built from source with default and minimum donation levels
set to zero. Modified source is in `releases/xmrig-6.26.0-source.tar.gz`;
see the rebuild instructions below.

The new launchers accept the same slot profile as the existing miners.
`addition` is split on whitespace into extra CLI arguments, without shell
evaluation. Statistics describe the first algorithm; CPU work is included in
totals but CPU threads are not reported as GPU devices.

Install archives contain only the launcher, stats adapter, binary,
`files.md5` and redistribution license notices. Build documentation and
modified source are kept separately from the installed miner.

### Rebuilding XMRig

The upstream tag is `v6.26.0`. The only code change is in `src/donate.h`:
`kDefaultDonateLevel` and `kMinimumDonateLevel` are changed from 1 to 0.
The launcher also sets `--donate-level 0 --donate-over-proxy 0`.

The complete modified source, upstream GPL-3.0 license and hwloc dependency
source are in `releases/xmrig-6.26.0-source.tar.gz`. The upstream source
archive SHA-256 before modification is
`bebb05cd95bc43e3d40b02abb98ea8680e68f2cb1c8bdaf442bde8f914c924ee`;
the hwloc 2.12.1 archive SHA-256 is
`ffa02c3a308275a9339fbe92add054fac8e9a00cb8fe8c53340094012cb7c633`.

On Ubuntu 24.04 x86_64, from the repository root:

```bash
sudo apt-get install build-essential cmake libuv1-dev libssl-dev
bash .github/scripts/build_xmrig.sh
```

The script rebuilds the binary and install archive. It uses static libuv
1.48.0, OpenSSL 3.0.13 and hwloc 2.12.1 with CPU, TLS and HTTP API support.
It does not use `-march=native`. Upstream disables OpenCL and CUDA for fully
static Linux binaries; KawPow is disabled because it requires a GPU backend.
GPU mining requires a separate dynamic build and an external CUDA plugin
for NVIDIA. This build was tested on Ubuntu 24.04.

## Slot profile

Both `miner` and `stats` receive a profile path as `$1`:

```json
{
  "slot": 0,
  "miner": "miniz",
  "fork": "2.5e3",
  "pool": "pool.example.com:1234",
  "wallet": "t1abc...",
  "pass": "x",
  "template": "t1abc....workerName",
  "algo": "144,5",
  "addition": "--extra-flag",
  "coin": "ZEC",
  "api_port": 20000,
  "extra": {}
}
```

| Field | Description |
|-------|-------------|
| `slot` | Slot index |
| `miner` | Miner ID (matches manifest `id`) |
| `fork` | Resolved version (not "latest") |
| `pool` | Pool address `host:port` |
| `wallet` | Wallet address |
| `pass` | Pool password |
| `template` | Wallet template (used in pool URL) |
| `algo` | Algorithm parameter (miner-specific, maps to `algos[].i` in manifest) |
| `addition` | Extra CLI flags passed to the miner |
| `coin` | Coin ticker |
| `api_port` | Local API port for stats collection |
| `extra` | Arbitrary extra data |
