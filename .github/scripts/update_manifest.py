#!/usr/bin/env python3
"""Update the srbminer entry in manifest.json from a SRBMiner --list-algorithms dump.

Reconciles the algo list (adds new GPU-mineable algos, drops ones removed
upstream, preserves existing order and any manual `i` overrides), bumps
`latest`, and prepends the new version URL (keeping the most recent N).

The manifest is rewritten with a custom serializer that reproduces the
repo's exact formatting, so unchanged miners stay byte-identical and diffs
show only what really changed.
"""
import argparse
import json
import re
import sys

URL_TEMPLATE = ("https://raw.githubusercontent.com/shatll-s/"
                "os.dog-plugins-miners-base/main/releases/srbminer-%s.tar.gz")

# A row from `--list-algorithms`, e.g. "[1.00%]   [ -  A  N  I ]   autolykos2"
# Groups: cpu, amd, nvidia, intel flag chars + the algo name.
ALGO_RE = re.compile(
    r"^\[\s*[\d.]+%\]\s*\[\s*(\S)\s+(\S)\s+(\S)\s+(\S)\s*\]\s+(\S+)\s*$")

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# CPU-only algos are normally excluded, but any already in the manifest are
# kept as long as upstream still ships them (see reconcile()). This keeps a
# deliberate CPU pick like randomx without auto-adding every CPU algo.


def parse_algolist(text):
    """Return (all_names, gpu_names) parsed from a --list-algorithms dump."""
    all_names, gpu_names = [], []
    for line in ANSI_RE.sub("", text).replace("\r", "").splitlines():
        m = ALGO_RE.match(line.strip())
        if not m:
            continue
        _cpu, amd, nvidia, intel, name = m.groups()
        all_names.append(name)
        if amd != "-" or nvidia != "-" or intel != "-":
            gpu_names.append(name)
    return all_names, gpu_names


def reconcile(existing, all_names, gpu_names):
    """Merge: keep existing entries still shipped upstream (in original
    order, preserving their g/i), then append newly-added GPU algos."""
    present = set(all_names)
    kept = [a for a in existing if a["g"] in present]
    kept_g = {a["g"] for a in kept}
    added = sorted(n for n in gpu_names if n not in kept_g)
    return kept + [{"g": n, "i": n} for n in added], added, \
        [a["g"] for a in existing if a["g"] not in present]


def update_versions(versions, version, keep):
    url = URL_TEMPLATE % version
    new = {version: url}
    for k, v in versions.items():
        if k != version:
            new[k] = v
    return dict(list(new.items())[:keep])


# ---- custom serializer that matches manifest.json's exact house style ----

def _scalar(v):
    return json.dumps(v, ensure_ascii=False)


def _dump_miner(m):
    out = ["    {"]
    keys = list(m)
    for i, k in enumerate(keys):
        tail = "," if i < len(keys) - 1 else ""
        if k == "algos":
            out.append('      "algos": [')
            algos = m["algos"]
            for j, a in enumerate(algos):
                ac = "," if j < len(algos) - 1 else ""
                out.append('        { "g": %s, "i": %s }%s'
                           % (_scalar(a["g"]), _scalar(a["i"]), ac))
            out.append("      ]" + tail)
        elif k == "versions":
            out.append('      "versions": {')
            items = list(m["versions"].items())
            for j, (vk, vv) in enumerate(items):
                vc = "," if j < len(items) - 1 else ""
                out.append('        %s: %s%s' % (_scalar(vk), _scalar(vv), vc))
            out.append("      }" + tail)
        else:
            out.append('      %s: %s%s' % (_scalar(k), _scalar(m[k]), tail))
    out.append("    }")
    return out


def dump(manifest):
    lines = ["{"]
    keys = list(manifest)
    for i, k in enumerate(keys):
        tail = "," if i < len(keys) - 1 else ""
        if k == "miners":
            lines.append('  "miners": [')
            miners = manifest["miners"]
            for j, m in enumerate(miners):
                block = _dump_miner(m)
                if j < len(miners) - 1:
                    block[-1] += ","
                lines.extend(block)
            lines.append("  ]" + tail)
        else:
            lines.append('  %s: %s%s' % (_scalar(k), _scalar(manifest[k]), tail))
    lines.append("}")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="manifest.json")
    ap.add_argument("--version", required=True)
    ap.add_argument("--algolist", help="file with raw --list-algorithms output")
    ap.add_argument("--keep-versions", type=int, default=3)
    ap.add_argument("--miner-id", default="srbminer")
    ap.add_argument("--min-algos", type=int, default=20,
                    help="if fewer algos parse, leave the algo list untouched")
    args = ap.parse_args()

    with open(args.manifest, encoding="utf-8") as f:
        manifest = json.load(f)

    srb = next((m for m in manifest["miners"] if m["id"] == args.miner_id), None)
    if srb is None:
        sys.exit("miner id %r not found in manifest" % args.miner_id)

    srb["latest"] = args.version
    srb["versions"] = update_versions(srb["versions"], args.version,
                                      args.keep_versions)

    if args.algolist:
        with open(args.algolist, encoding="utf-8", errors="replace") as f:
            all_names, gpu_names = parse_algolist(f.read())
        if len(all_names) < args.min_algos:
            print("WARN: parsed only %d algos (<%d); keeping existing algo list"
                  % (len(all_names), args.min_algos), file=sys.stderr)
        else:
            srb["algos"], added, removed = reconcile(
                srb["algos"], all_names, gpu_names)
            print("algos: +%d %s / -%d %s / total %d"
                  % (len(added), added, len(removed), removed,
                     len(srb["algos"])), file=sys.stderr)

    with open(args.manifest, "w", encoding="utf-8") as f:
        f.write(dump(manifest))


if __name__ == "__main__":
    main()
