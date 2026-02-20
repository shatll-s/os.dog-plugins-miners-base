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
