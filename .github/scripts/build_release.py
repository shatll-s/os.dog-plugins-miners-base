#!/usr/bin/env python3
"""Verify and package OneZeroMiner/BzMiner; reconcile their actual algorithms."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import urllib.request

from miner_algorithms import parse_bz_algos, parse_onezero_help, parse_onezero_readme, reconcile
from update_manifest import dump

ROOT = Path(__file__).resolve().parents[2]
REPOS = {"onezerominer": "OneZeroMiner/onezerominer", "bzminer": "bzminer/bzminer"}


def request(url, accept="application/vnd.github+json"):
    headers = {"Accept": accept, "User-Agent": "os.dog-miner-builder"}
    if os.environ.get("GH_TOKEN") and url.startswith("https://api.github.com/"):
        headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120)


def build(miner, version=None, release_file=None, archive_file=None, readme_file=None):
    forced = bool(version)
    repo = REPOS[miner]
    if release_file:
        release = json.loads(Path(release_file).read_text())
    else:
        endpoint = "tags/v" + version.removeprefix("v") if version else "latest"
        with request(f"https://api.github.com/repos/{repo}/releases/{endpoint}") as response:
            release = json.load(response)
    tag = release["tag_name"]
    version = tag.removeprefix("v")
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+(?:[a-z0-9.-]*)?", version):
        raise ValueError(f"Unexpected release version: {tag}")
    manifest_path = ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    entry = next(m for m in manifest["miners"] if m["id"] == miner)
    if entry["latest"] == version and not archive_file and not forced:
        print(f"{miner} {version}: already current")
        return
    name = f"onezerominer-{version}.tar.gz" if miner == "onezerominer" else f"bzminer_v{version}_linux.tar.gz"
    asset = next(a for a in release["assets"] if a["name"] == name)
    digest = asset.get("digest") or ""
    if not digest.startswith("sha256:"):
        # Older releases sometimes publish hashes only in the release body.
        match = re.search(re.escape(name) + r"[^\n]*?\b([a-fA-F0-9]{64})\b", release.get("body", ""))
        if not match:
            raise ValueError(f"No upstream SHA-256 for {name}")
        digest = "sha256:" + match[1].lower()
    with tempfile.TemporaryDirectory(prefix=f"osdog-{miner}-") as tmp:
        tmp = Path(tmp)
        if archive_file:
            archive = Path(archive_file)
        else:
            archive = tmp / name
            with request(asset["url"], "application/octet-stream") as response, archive.open("wb") as out:
                while chunk := response.read(1024 * 1024):
                    out.write(chunk)
        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        if actual != digest.split(":", 1)[1]:
            raise ValueError(f"SHA-256 mismatch for {name}")
        unpacked = tmp / "unpacked"
        unpacked.mkdir()
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                    raise ValueError(f"Unexpected archive member: {member.name}")
                target = (unpacked / member.name).resolve()
                if not target.is_relative_to(unpacked.resolve()):
                    raise ValueError(f"Unsafe archive path: {member.name}")
            tar.extractall(unpacked)
        binaries = [p for p in unpacked.rglob(miner) if p.is_file()]
        if len(binaries) != 1:
            raise ValueError(f"Expected exactly one {miner} executable")
        binary = binaries[0]
        binary.chmod(0o755)
        if miner == "bzminer":
            output = subprocess.check_output([str(binary), "--list-algos"], cwd=tmp, text=True, timeout=60)
            data = json.loads(output)
            if data["version"].removeprefix("v") != version:
                raise ValueError("BzMiner binary version differs from release")
            names = parse_bz_algos(output)
        else:
            probe = subprocess.run([str(binary), "--version"], cwd=tmp, capture_output=True, text=True, timeout=60)
            said = (probe.stdout + probe.stderr).strip()
            if probe.returncode and "no supported gpu" in said.lower():
                # Since 1.7.9 the binary looks for a GPU before it parses any flag, so a build
                # runner gets neither --version nor --help. Check the packaged version instead
                # and keep the known algorithms: only the binary could prove one was removed.
                conf = binary.parent / "h-manifest.conf"
                packaged = re.search(r"^CUSTOM_VERSION=(\S+)$", conf.read_text() if conf.is_file() else "", re.M)
                if not packaged or packaged[1] != version:
                    raise ValueError("OneZeroMiner package version differs from release")
                names = [a["i"] for a in entry["algos"]]
            elif probe.returncode:
                raise ValueError(f"OneZeroMiner --version exited {probe.returncode}: {said[-300:]}")
            else:
                if not re.search(r"(?<![0-9.])" + re.escape(version) + r"(?![0-9.])", probe.stdout):
                    raise ValueError("OneZeroMiner binary version differs from release")
                output = subprocess.check_output([str(binary), "--help"], cwd=tmp, text=True, timeout=60)
                names = parse_onezero_help(output)
            if readme_file:
                readme = Path(readme_file).read_text()
            else:
                with request(f"https://raw.githubusercontent.com/{repo}/{release['target_commitish']}/README.md", "text/plain") as response:
                    readme = response.read().decode()
            names += parse_onezero_readme(readme)
        algorithms = reconcile(entry["algos"], names)
        if not algorithms:
            raise ValueError("Refusing to publish an empty algorithm list")
        destination = ROOT / "miners" / miner
        files = {"miner": (destination / "miner").read_bytes(),
                 "stats": (destination / "stats").read_bytes(), miner: binary.read_bytes()}
        notices = binary.parent / "THIRD_PARTY_NOTICES.txt"
        if notices.is_file():
            files[notices.name] = notices.read_bytes()
        checksums = "".join(f"{hashlib.md5(data).hexdigest()}  ./{name}\n" for name, data in files.items())
        (tmp / "package").mkdir()
        for name, data in files.items():
            path = tmp / "package" / name
            path.write_bytes(data)
            path.chmod(0o755 if name in ("miner", "stats", miner) else 0o644)
        (tmp / "package/files.md5").write_text(checksums)
        release_path = ROOT / "releases" / f"{miner}-{version}.tar.gz"
        with tarfile.open(release_path, "w:gz") as tar:
            for path in sorted((tmp / "package").iterdir()):
                tar.add(path, arcname="./" + path.name)
        (destination / miner).write_bytes(files[miner])
        (destination / miner).chmod(0o755)
        if notices.is_file():
            (destination / notices.name).write_bytes(files[notices.name])
        entry["latest"] = version
        entry["algos"] = algorithms
        versions = {version: f"https://raw.githubusercontent.com/shatll-s/os.dog-plugins-miners-base/main/releases/{miner}-{version}.tar.gz"}
        versions.update({k: v for k, v in entry["versions"].items() if k != version})
        entry["versions"] = versions
        manifest_path.write_text(dump(manifest))
        print(f"Packaged {miner} {version}, {len(algorithms)} algorithms, upstream SHA-256 verified")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--miner", choices=REPOS, required=True)
    parser.add_argument("--version", help="blank = latest stable upstream release")
    parser.add_argument("--release-json", help="use saved GitHub release metadata")
    parser.add_argument("--archive", help="use a previously downloaded archive (still verified)")
    parser.add_argument("--readme", help="use saved OneZeroMiner README")
    args = parser.parse_args()
    build(args.miner, args.version, args.release_json, args.archive, args.readme)
