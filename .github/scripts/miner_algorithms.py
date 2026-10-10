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
    names = re.findall(r"^\s*-\s+([a-z0-9_]+)\s*$", match[1], re.M)
    if len(names) < 5:
        raise ValueError("Incomplete OneZeroMiner algorithm list")
    return names


def parse_onezero_readme(text):
    # The binary's help omits pearlhash in 1.7.8. Only read the active table,
    # never examples or the outdated dual-mining pairs below it.
    match = re.search(r"^(?:#+\s*)?Supported algorithms\s*\n(.*?)(?=\n(?:#+\s*)?Supported dual mining pairs|\n## |\Z)", text, re.S | re.M)
    if not match:
        raise ValueError("OneZeroMiner README algorithm table missing")
    return re.findall(r"^\|?\s*([a-z][a-z0-9_]*)\s*\|", match[1], re.M)


def parse_neko_readme(text):
    # Stop at the collapsed "Deprecated algorithms" table, which has the same header.
    # A row starts with the -a value; an alias may follow it in the same cell.
    match = re.search(r"^## Supported Algorithms\s*\n(.*?)(?=\n<details>|\n## |\Z)", text, re.S | re.M)
    names = re.findall(r"^\|\s*`([a-z0-9_]+)`", match[1], re.M) if match else []
    if len(names) < 3:
        raise ValueError("nekominer README algorithm table missing or incomplete")
    return names


def parse_bz_algos(text):
    rows = json.loads(text)["algorithms"]
    if len(rows) < 5:
        raise ValueError("Incomplete BzMiner algorithm list")
    names = set()
    for row in rows:
        name = row["name"]
        if name.startswith("cryptonight/") or name.startswith("cryptonight-heavy/") or name.startswith("cryptonight-lite/"):
            name = name.replace("cryptonight", "cn", 1)
        names.add(BZ_ALIASES.get(name, name))
    return sorted(names)


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
