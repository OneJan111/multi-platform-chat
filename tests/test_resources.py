import os
import tempfile
import unittest
from unittest import mock

from src import resources


class ResourcesTests(unittest.TestCase):
    def setUp(self):
        self._saved = (resources._STATE["last"], list(resources._STATE["history"]))
        resources._STATE["last"] = None
        resources._STATE["history"].clear()

    def tearDown(self):
        resources._STATE["last"] = self._saved[0]
        resources._STATE["history"].clear()
        resources._STATE["history"].extend(self._saved[1])

    def test_sample_needs_two_measurements_then_reports_rates(self):
        self.assertEqual(resources.sample(), [])
        self.assertEqual(resources.sample(), [])  # too soon: no new measurement
        resources._STATE["last"]["wall"] -= resources.MIN_INTERVAL + 1
        resources._STATE["last"]["net_recv"] -= 4096
        history = resources.sample()
        self.assertEqual(len(history), 1)
        entry = history[0]
        self.assertGreater(entry["app_ram"], 0)
        self.assertGreater(entry["threads"], 0)
        self.assertGreaterEqual(entry["recv"], 4096 / (resources.MIN_INTERVAL + 2))
        for key in ("app_cpu", "sys_cpu"):
            if entry[key] is not None:
                self.assertTrue(0 <= entry[key] <= 100, key)
        self.assertLessEqual(entry["ram_used"], entry["ram_total"])

    def test_container_limits_v2_and_v1(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(resources.container_limits(root), {})
            for name, value in {"memory.max": "536870912", "memory.current": "104857600",
                                "cpu.max": "150000 100000"}.items():
                with open(os.path.join(root, name), "w") as f:
                    f.write(value + "\n")
            self.assertEqual(resources.container_limits(root),
                             {"memory": 536870912, "memory_used": 104857600, "cpus": 1.5})
        with tempfile.TemporaryDirectory() as root:
            for name, value in {"memory.max": "max", "cpu.max": "max 100000"}.items():
                with open(os.path.join(root, name), "w") as f:
                    f.write(value)
            self.assertEqual(resources.container_limits(root), {})  # cgroup v2 without limits
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "memory"))
            os.makedirs(os.path.join(root, "cpu"))
            for name, value in {"memory/memory.limit_in_bytes": str(1 << 62),
                                "cpu/cpu.cfs_quota_us": "200000", "cpu/cpu.cfs_period_us": "100000"}.items():
                with open(os.path.join(root, name), "w") as f:
                    f.write(value)
            self.assertEqual(resources.container_limits(root), {"cpus": 2.0})  # v1 "unlimited" memory

    def test_container_cpu_limit_scales_app_cpu_and_hides_host_cpu(self):
        resources.sample()
        resources._STATE["last"]["wall"] -= 10
        resources._STATE["last"]["proc_cpu_s"] -= 5  # 5 CPU-seconds in 10 s = half a core
        with mock.patch.object(resources, "container_limits", return_value={"cpus": 1.0}):
            entry = resources.sample()[-1]
        self.assertIsNone(entry["sys_cpu"])
        self.assertAlmostEqual(entry["app_cpu"], 50, delta=5)
        self.assertTrue(entry["container"])

    def test_format_bytes(self):
        self.assertEqual(resources.format_bytes(512), "512 B")
        self.assertEqual(resources.format_bytes(1536), "1.5 KB")
        self.assertEqual(resources.format_bytes(3 * 2**30), "3.0 GB")
        self.assertEqual(resources.format_bytes(5 * 2**40), "5120.0 GB")


if __name__ == "__main__":
    unittest.main()
