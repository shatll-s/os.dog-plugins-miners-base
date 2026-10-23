"""Dev fees in manifest.json: records that apply from their version on (see README, "Dev fees")."""
import re


def version_key(version):
    """Sort key for miner versions: 0.14.9 < 0.14.60, 1.9 < 1.10, 1.98 < 1.98a, 2.5e2 < 2.5e3.

    Digit groups compare as numbers and other groups as text; at the same position a
    number is greater than text. Separators (. - _) and a leading v are ignored, trailing
    zero groups don't count (1.2 == 1.2.0), and a version is newer than its own prefix,
    so "0" is older than any version. Pre-releases get no special treatment: 1.0.0-rc1
    comes out newer than 1.0.0.
    """
    groups = re.findall(r"\d+|[^\d._-]+", re.sub(r"^[vV]", "", version.strip()))
    key = [(1, int(g), "") if g.isdigit() else (0, 0, g) for g in groups]
    while key and key[-1] == (1, 0, ""):
        key.pop()
    return key


def fee_in_force(fees, version, algo):
    """The fee of `algo` in `version`: a number, or None when unknown (no record, or null)."""
    keys = [k for k, record in fees.items()
            if isinstance(record, dict) and algo in record and version_key(k) <= version_key(version)]
    return fees[max(keys, key=version_key)][algo] if keys else None


def record_fees(entry, version, found):
    """Add a record for `version` with every fee in `found` ({g: percent}) that differs
    from the one in force, and return those fees. Records stay in version order and a
    record's algorithms in the order of `algos`; malformed data is left as it is."""
    fees = entry.get("fees", {})
    if not isinstance(fees, dict) or not isinstance(fees.get(version, {}), dict):
        return {}
    changed = {g: int(fee) if float(fee).is_integer() else fee
               for g, fee in found.items() if fee_in_force(fees, version, g) != fee}
    if changed:
        rank = {a["g"]: n for n, a in enumerate(entry["algos"])}
        record = {**fees.get(version, {}), **changed}
        fees = {**fees, version: dict(sorted(record.items(), key=lambda kv: rank.get(kv[0], len(rank))))}
        entry["fees"] = dict(sorted(fees.items(), key=lambda kv: version_key(kv[0])))
    return changed
