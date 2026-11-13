"""Package the rgminer binary with the regular os.dog adapters."""
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
        for name in ("miner", "stats", "rgminer"):
            shutil.copy2(source / name, stage / name)
        for name in ("miner", "stats", "rgminer"):
            (stage / name).chmod(0o755)
        (stage / "files.md5").write_text("".join(
            f"{hashlib.md5((stage / name).read_bytes()).hexdigest()}  ./{name}\n"
            for name in ("miner", "stats", "rgminer")))
        with tarfile.open(ROOT / "releases" / f"rgminer-{version}.tar.gz", "w:gz") as archive:
            for name in ("miner", "stats", "rgminer", "files.md5"):
                archive.add(stage / name, arcname="./" + name)


if __name__ == "__main__":
    package("1.1.5")
