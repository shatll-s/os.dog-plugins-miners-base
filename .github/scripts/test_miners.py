"""Regression checks for the new adapters and automatic algorithm updates."""
import contextlib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from miner_algorithms import parse_bz_algos, parse_onezero_help, parse_onezero_readme, reconcile
from update_manifest import reconcile as reconcile_srb

ROOT = Path(__file__).resolve().parents[2]


@contextlib.contextmanager
def api(responses):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in responses:
                self.send_error(404)
                return
            self.send_response(200)
            self.end_headers()
            data = responses[self.path]
            self.wfile.write(data if isinstance(data, bytes) else json.dumps(data).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def stats(miner, responses):
    with api(responses) as port, tempfile.TemporaryDirectory() as tmp:
        profile = Path(tmp) / "profile.json"
        profile.write_text(json.dumps({"api_port": port}))
        return subprocess.run([str(ROOT / "miners" / miner / "stats"), str(profile)],
                              capture_output=True, text=True, timeout=10)


class AlgorithmTests(unittest.TestCase):
    def test_reconcile_removes_obsolete_and_keeps_mapping(self):
        existing = [{"g": "custom_name", "i": "kept"}, {"g": "old", "i": "removed"}]
        self.assertEqual(reconcile(existing, ["kept", "rx/0", "rx/0"]),
                         [{"g": "custom_name", "i": "kept"}, {"g": "randomx", "i": "rx/0"}])

    def test_srb_includes_new_cpu_algorithm(self):
        existing = [{"g": "custom_name", "i": "gpu"}, {"g": "old", "i": "removed"}]
        result, added, removed = reconcile_srb(existing, ["gpu", "cpu"], ["gpu"])
        self.assertEqual(result, [{"g": "custom_name", "i": "gpu"}, {"g": "cpu", "i": "cpu"}])
        self.assertEqual((added, removed), (["cpu"], ["old"]))

    def test_onezero_active_table_excludes_old_dual_pair(self):
        help_text = "Currently supported algorithms are:\n" + "".join(
            "\t- " + a + "\n" for a in ["dynex", "xelishashv3", "cryptix_ox8", "qhash", "quantus", "zilliqa"])
        help_text += "\n --a2 <algo2>"
        readme = "Supported algorithms\n------\nAlgorithm | Nvidia | AMD\npearlhash | 1% | x\n\nSupported dual mining pairs\n------\nxelishashv2-qhash (Nvidia only)\n"
        names = parse_onezero_help(help_text) + parse_onezero_readme(readme)
        self.assertIn("pearlhash", names)
        self.assertNotIn("xelishashv2", names)

    def test_bad_algorithm_dump_fails_closed(self):
        with self.assertRaises(ValueError):
            parse_onezero_help("library load failure")
        with self.assertRaises(ValueError):
            parse_bz_algos('{"algorithms": []}')

    def test_bz_aliases_are_deduplicated(self):
        names = ["ergo", "kawpow", "rvn", "pearl", "pearlhash", "randomx", "xmr", "cn/gpu", "cryptonight-gpu"]
        data = json.dumps({"algorithms": [{"name": name} for name in names]})
        self.assertEqual(parse_bz_algos(data), ["cn/gpu", "ergo", "kawpow", "pearl", "randomx"])


class StatsTests(unittest.TestCase):
    def test_xmrig_cpu_total_and_gpu_worker_aggregation(self):
        summary = {"version": "6.26.0", "uptime": 10, "connection": {"algo": "rx/0"},
                   "hashrate": {"total": [125.75, None, None]},
                   "results": {"shares_good": 7, "shares_total": 9}}
        backends = [{"type": "cpu", "threads": [{"hashrate": [100]}]},
                    {"type": "opencl", "threads": [
                        {"bus_id": "0A:00.0", "hashrate": [12.5]},
                        {"bus_id": "0A:00.0", "hashrate": [13.25]}]}]
        result = stats("xmrig", {"/2/summary": summary, "/2/backends": backends})
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["total_hr"], "125.75")
        self.assertEqual(data["total_badshare"], "2")
        self.assertEqual(data["hr"], [25.75])
        self.assertEqual(data["busid"], {"0": "0a"})

    def test_xmrig_missing_optional_backends_keeps_cpu_stats(self):
        result = stats("xmrig", {"/2/summary": {"version": "6.26.0", "hashrate": {"total": [None, 42.5]}, "results": {}}})
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["total_hr"], "42.5")
        self.assertNotIn("hr", data)

    def test_onezero_numeric_pci_bus_and_fractional_hashrate(self):
        response = {"version": "1.7.8", "uptime_seconds": 12,
                    "devices": [{"bus_id": 10, "temp": None, "fan": None}],
                    "algos": [{"name": "pearlhash", "total_hashrate": 0.125,
                               "hashrates": [0.125], "total_accepted_shares": 4,
                               "total_rejected_shares": 1, "devices_accepted_shares": [4],
                               "devices_rejected_shares": [1]}]}
        result = stats("onezerominer", {"/": response})
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["busid"], {"0": "0a"})
        self.assertEqual(data["total_hr"], "0.125")
        self.assertEqual(data["share"], [4])
        self.assertNotIn("temp", data)

    def test_bz_cpu_excluded_from_gpu_arrays_but_in_totals(self):
        response = {"bzminer_version": "v100.45", "uptime_s": 10,
                    "pools": [{"algorithm": "pearl"}], "devices": [
                        {"vendor": 4, "hashrate": [10], "valid_solutions": [3]},
                        {"vendor": 1, "pci_bus_id": 171, "hashrate": [0.25],
                         "valid_solutions": [2], "invalid_solutions": [1],
                         "rejected_solutions": [2], "core_temp": 60, "fan": 50}]}
        result = stats("bzminer", {"/status": response})
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["total_hr"], "10.25")
        self.assertEqual(data["total_share"], "5")
        self.assertEqual(data["total_badshare"], "3")
        self.assertEqual(data["hr"], [0.25])
        self.assertEqual(data["busid"], {"0": "ab"})

    def test_invalid_api_data_fails(self):
        for miner, path in [("xmrig", "/2/summary"), ("onezerominer", "/"), ("bzminer", "/status")]:
            with self.subTest(miner=miner):
                result = stats(miner, {path: b"not JSON"})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")


class PackageTests(unittest.TestCase):
    def test_corrupt_upstream_archive_does_not_mutate_manifest(self):
        import build_release
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "manifest.json"
            original = json.dumps({"miners": [{"id": "bzminer", "latest": "1.0", "algos": [], "versions": {}}]})
            manifest.write_text(original)
            release = root / "release.json"
            release.write_text(json.dumps({"tag_name": "v2.0", "assets": [{
                "name": "bzminer_v2.0_linux.tar.gz", "digest": "sha256:" + "0" * 64}]}))
            archive = root / "corrupt.tar.gz"
            archive.write_bytes(b"corrupt archive")
            with patch.object(build_release, "ROOT", root), self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                build_release.build("bzminer", release_file=release, archive_file=archive)
            self.assertEqual(manifest.read_text(), original)
            self.assertFalse((root / "releases").exists())

    def test_release_checksums_and_source_match_repository(self):
        import tarfile
        manifest = json.loads((ROOT / "manifest.json").read_text())
        for miner in ("xmrig", "onezerominer", "bzminer"):
            entry = next(m for m in manifest["miners"] if m["id"] == miner)
            with self.subTest(miner=miner), tarfile.open(ROOT / "releases" / f"{miner}-{entry['latest']}.tar.gz") as tar:
                allowed = {"./miner", "./stats", "./" + miner, "./files.md5"}
                if miner == "xmrig":
                    allowed.add("./LICENSE")
                elif miner == "bzminer":
                    allowed.add("./THIRD_PARTY_NOTICES.txt")
                self.assertEqual(set(tar.getnames()), allowed)
                checksums = tar.extractfile("./files.md5").read().decode()
                for line in checksums.splitlines():
                    digest, name = line.split(maxsplit=1)
                    data = tar.extractfile(name).read()
                    self.assertEqual(hashlib.md5(data).hexdigest(), digest)
                    self.assertEqual(data, (ROOT / "miners" / miner / name.removeprefix("./")).read_bytes())
                for name in ("miner", "stats", miner):
                    self.assertTrue(tar.getmember("./" + name).mode & 0o111)


if __name__ == "__main__":
    unittest.main()
