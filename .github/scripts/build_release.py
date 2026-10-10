#!/usr/bin/env python3
"""Verify and package OneZeroMiner/BzMiner, link nekominer's own package; reconcile their actual algorithms."""
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

from miner_algorithms import parse_bz_algos, parse_neko_readme, parse_onezero_help, parse_onezero_readme, reconcile
from update_manifest import dump

ROOT = Path(__file__).resolve().parents[2]
REPOS = {"onezerominer": "OneZeroMiner/onezerominer", "bzminer": "bzminer/bzminer", "nekominer": "nr800/nekominer"}
ASSETS = {"onezerominer": "onezerominer-{}.tar.gz", "bzminer": "bzminer_v{}_linux.tar.gz",
          "nekominer": "nekominer-osdog-{}.tar.gz"}


def request(url, accept="application/vnd.github+json"):
    headers = {"Accept": accept, "User-Agent": "os.dog-miner-builder"}
    if os.environ.get("GH_TOKEN") and url.startswith("https://api.github.com/"):
        headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120)


def read_readme(repo, ref, readme_file):
    if readme_file:
        return Path(readme_file).read_text()
    with request(f"https://raw.githubusercontent.com/{repo}/{ref}/README.md", "text/plain") as response:
        return response.read().decode()


def check_package(package, miner):
    """Rigs install upstream's os.dog package as is: it must be complete and match its own checksums."""
    sums = {}
    for line in (package / "files.md5").read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        sums[name.removeprefix("*").removeprefix("./")] = digest
    for name in ("miner", "stats", miner):
        if name not in sums or not os.access(package / name, os.X_OK):
            raise ValueError(f"Upstream package has no executable {name}")
    for name, digest in sums.items():
        if Path(name).name != name or hashlib.md5((package / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Upstream package checksum mismatch for {name}")


def publish(manifest_path, manifest, entry, version, algorithms, url):
    entry["latest"] = version
    entry["algos"] = algorithms
    versions = {version: url}
    versions.update({k: v for k, v in entry["versions"].items() if k != version})
    entry["versions"] = versions
    manifest_path.write_text(dump(manifest))


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
    name = ASSETS[miner].format(version)
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
        elif miner == "nekominer":
            # The binary needs the NVIDIA driver even for --help, so the list comes from the
            # README of the release tag.
            check_package(binary.parent, miner)
            names = parse_neko_readme(read_readme(repo, tag, readme_file))
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
            names += parse_onezero_readme(read_readme(repo, release.get("target_commitish", "HEAD"), readme_file))
        algorithms = reconcile(entry["algos"], names)
        if not algorithms:
            raise ValueError("Refusing to publish an empty algorithm list")
        if miner == "nekominer":
            # Nothing to package: upstream's archive is the os.dog package, the manifest links to it.
            publish(manifest_path, manifest, entry, version, algorithms, asset["browser_download_url"])
            print(f"Linked {miner} {version}, {len(algorithms)} algorithms, upstream SHA-256 verified")
            return
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
        publish(manifest_path, manifest, entry, version, algorithms,
                f"https://raw.githubusercontent.com/shatll-s/os.dog-plugins-miners-base/main/releases/{miner}-{version}.tar.gz")
        print(f"Packaged {miner} {version}, {len(algorithms)} algorithms, upstream SHA-256 verified")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--miner", choices=REPOS, required=True)
    parser.add_argument("--version", help="blank = latest stable upstream release")
    parser.add_argument("--release-json", help="use saved GitHub release metadata")
    parser.add_argument("--archive", help="use a previously downloaded archive (still verified)")
    parser.add_argument("--readme", help="use a saved upstream README")
    args = parser.parse_args()
    build(args.miner, args.version, args.release_json, args.archive, args.readme)
