"""Read supported algorithms and preserve os.dog's names across releases."""
import json
import re

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# Common names must match the existing base package, not miner aliases.
SYSTEM_NAMES = {
    "rx/0": "randomx", "rx/2": "randomxv2",
    "rx/wow": "randomwow", "rx/arq": "randomarq", "rx/graft": "randomgraft",
    "rx/sfx": "randomsfx", "rx/yada": "randomyada",
    "cn/0": "cryptonight", "cn/1": "cryptonight_v7",
    "cn/2": "cryptonight_v8", "cn/r": "cryptonight_r",
    "cn/gpu": "cryptonight_gpu", "cn-pico": "cryptonight_turtle",
    "cn-pico/0": "cryptonight_turtle", "cn-pico/trtl": "cryptonight_turtle",
    "cn/upx2": "cryptonight_upx2", "ergo": "autolykos2",
    "pearl": "pearlhash", "xelis": "xelishashv3",
    "warthog": "janushash", "verus": "verushash",
    "zilliqa": "zil",
    # Parano1d: OneZeroMiner's poseidon2b is SRBMiner's noid.
    "poseidon2b": "noid",
}

# BzMiner lists aliases as independent rows. Keep one parameter per PoW.
BZ_ALIASES = {
    "clore": "kawpow", "rvn": "kawpow", "ravencoin": "kawpow",
    "neox": "kawpow", "neoxa": "kawpow", "neurai": "kawpow",
    "xna": "kawpow", "meowcoin": "kawpow", "mewc": "kawpow",
    "etc": "etchash", "ethw": "ethash", "ethereumpow": "ethash",
    "xmr": "randomx", "monero": "randomx", "rx/0": "randomx",
    "zeph": "randomx", "zephyr": "randomx", "sal": "randomx", "salvium": "randomx",
    "pearlhash": "pearl", "cn": "cn/0",
    "cn-gpu": "cn/gpu", "cn_gpu": "cn/gpu",
    "cn-heavy": "cn-heavy/0", "cn-light": "cn-lite/0", "cn-lite": "cn-lite/0",
    "cn-pico/0": "cn-pico", "cn-pico/trtl": "cn-pico",
    "cn-talleo": "cn-pico/tlo", "cn-trtl": "cn-pico",
    "cn-ultralite": "cn-pico", "cn/ultra": "cn-pico",
    "cn-extremelite/upx2": "cn/upx2", "cn/msr": "cn/fast", "cn/conceal": "cn/ccx",
    "cryptonight": "cn/0", "cryptonight-aeonv7": "cn-lite/1",
    "cryptonight-conceal": "cn/ccx", "cryptonight-gpu": "cn/gpu",
    "cryptonight-haven": "cn-heavy/xhv", "cryptonight-monerov7": "cn/1",
    "cryptonight-monerov8": "cn/2", "cryptonight-turtle": "cn-pico",
    "cryptonight-upx/2": "cn/upx2",
}


def parse_onezero_help(text):
    text = ANSI_RE.sub("", text)
    match = re.search(r"Currently supported algorithms are:\s*(.*?)\n\s*--a2", text, re.S)
    if not match:
        raise ValueError("OneZeroMiner supported-algorithm section missing")
    # Since 1.8.2 a line may name aliases: "- poseidon2b (aliases: parano1d, noid)".
    names = re.findall(r"^\s*-\s+([a-z0-9_]+)(?:\s+\([^)]*\))?\s*$", match[1], re.M)
    if len(names) < 5:
        raise ValueError("Incomplete OneZeroMiner algorithm list")
    return names


# The binary's help omits pearlhash in 1.7.8. Only read the active table,
# never examples or the outdated dual-mining pairs below it. A name may carry
# an alias in brackets: "poseidon2b(noid)".
ONEZERO_TABLE_RE = re.compile(r"^(?:#+\s*)?Supported algorithms\s*\n(.*?)(?=\n(?:#+\s*)?Supported dual mining pairs|\n## |\Z)", re.S | re.M)
ONEZERO_ROW_RE = re.compile(r"^\|?\s*([a-z][a-z0-9_]*)(?:\s*\([^)|]*\))?\s*\|(.*)$", re.M)
# Stop at the collapsed "Deprecated algorithms" table, which has the same header.
NEKO_TABLE_RE = re.compile(r"^## Supported Algorithms\s*\n(.*?)(?=\n<details>|\n## |\Z)", re.S | re.M)


def fee_percent(cell):
    """The first percentage in a fee cell ("2%", "2%, 0% on <pool>"); "none" is 0."""
    if cell.strip().lower() == "none":
        return 0.0
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", cell)
    return float(match[1]) if match else None


def parse_onezero_readme(text):
    match = ONEZERO_TABLE_RE.search(text)
    if not match:
        raise ValueError("OneZeroMiner README algorithm table missing")
    return [name for name, _ in ONEZERO_ROW_RE.findall(match[1])]


def onezero_readme_fees(text):
    """{algorithm: fee %} from the NVIDIA and AMD columns; a row where they differ is left out."""
    match = ONEZERO_TABLE_RE.search(text)
    fees = {}
    for name, cells in ONEZERO_ROW_RE.findall(match[1] if match else ""):
        found = {fee_percent(c) for c in cells.split("|") if c.strip() and c.strip().lower() != "x"}
        if len(found) == 1 and None not in found:
            fees[name] = found.pop()
    return fees


def parse_neko_readme(text):
    # A row starts with the -a value; an alias may follow it in the same cell.
    match = NEKO_TABLE_RE.search(text)
    names = re.findall(r"^\|\s*`([a-z0-9_]+)`", match[1], re.M) if match else []
    if len(names) < 3:
        raise ValueError("nekominer README algorithm table missing or incomplete")
    return names


def neko_readme_fees(text):
    """{-a value: fee %} from the "Dev Fee" column of the active table."""
    match = NEKO_TABLE_RE.search(text)
    rows = [line.strip().strip("|").split("|") for line in (match[1] if match else "").splitlines()
            if line.strip().startswith("|")]
    header = next((cells for cells in rows if any("fee" in c.lower() for c in cells)), None)
    if not header:
        return {}
    column = next(n for n, c in enumerate(header) if "fee" in c.lower())
    fees = {}
    for cells in rows:
        name = re.match(r"\s*`([a-z0-9_]+)`", cells[0])
        if name and len(cells) > column and (fee := fee_percent(cells[column])) is not None:
            fees[name[1]] = fee
    return fees


def bz_name(name):
    if name.startswith("cryptonight/") or name.startswith("cryptonight-heavy/") or name.startswith("cryptonight-lite/"):
        name = name.replace("cryptonight", "cn", 1)
    return BZ_ALIASES.get(name, name)


def parse_bz_algos(text):
    rows = json.loads(text)["algorithms"]
    if len(rows) < 5:
        raise ValueError("Incomplete BzMiner algorithm list")
    return sorted({bz_name(row["name"]) for row in rows})


def bz_algo_fees(text):
    """{algorithm: fee %} from --list-algos under parse_bz_algos' names; aliases that disagree are left out."""
    fees, clash = {}, set()
    for row in json.loads(text)["algorithms"]:
        fee = row.get("dev_fee")
        if isinstance(fee, bool) or not isinstance(fee, (int, float)):
            continue
        name = bz_name(row["name"])
        if fees.setdefault(name, float(fee)) != fee:
            clash.add(name)
    return {name: fee for name, fee in fees.items() if name not in clash}


def reconcile(existing, names):
    """Match on implementation parameter, retaining manual system mappings."""
    names = list(dict.fromkeys(names))
    kept = [a for a in existing if a["i"] in names]
    used_i = {a["i"] for a in kept}
    used_g = {a["g"] for a in kept}
    for name in names:
        system = SYSTEM_NAMES.get(name, name)
        if name not in used_i and system not in used_g:
            kept.append({"g": system, "i": name})
            used_g.add(system)
    return kept
