"""Package the rgminer binary with the regular os.dog adapters."""
import argparse
import hashlib
from pathlib import Path
import shutil
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def package(version):
    source = ROOT / "miners" / "rgminer"
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        for name in ("miner", "stats", "rgminer", "profile.sh"):
            shutil.copy2(source / name, stage / name)
        for name in ("miner", "stats", "rgminer"):
            (stage / name).chmod(0o755)
        (stage / "files.md5").write_text("".join(
            f"{hashlib.md5((stage / name).read_bytes()).hexdigest()}  ./{name}\n"
            for name in ("miner", "stats", "rgminer", "profile.sh")))
        with tarfile.open(ROOT / "releases" / f"rgminer-{version}.tar.gz", "w:gz") as archive:
            for name in ("miner", "stats", "rgminer", "profile.sh", "files.md5"):
                archive.add(stage / name, arcname="./" + name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", nargs="?", default="1.1.5")
    package(parser.parse_args().version)
