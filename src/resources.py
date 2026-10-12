"""Resource usage of the server running this app: the app's own process, the machine (or container), network."""
from __future__ import annotations

import collections
import os
import sys
import threading
import time

import psutil

HISTORY = 120  # samples kept (about 10 minutes at the dashboard's refresh rate)
MIN_INTERVAL = 2.0  # several open dashboards share the samples; don't measure more often than this
# Streamlit re-imports edited modules; keep the history and counters on `sys`, which survives reloads.
_STATE = sys.__dict__.setdefault("_multi_platform_chat_resources", {
    "lock": threading.Lock(), "history": collections.deque(maxlen=HISTORY), "last": None,
})


def _read(path: str) -> str:
    try:
        with open(path, encoding="ascii") as f:
            return f.read().strip()
    except (OSError, UnicodeDecodeError):
        return ""


def container_limits(root: str = "/sys/fs/cgroup") -> dict:
    """Linux container (cgroup) limits: {"memory": bytes, "memory_used": bytes, "cpus": cores}; {} when unlimited.

    In a container psutil reports the host's totals, so these are what the app is actually allowed."""
    out: dict = {}
    mem = _read(f"{root}/memory.max") or _read(f"{root}/memory/memory.limit_in_bytes")
    # cgroup v1 reports "no limit" as a huge number.
    if mem.isdigit() and int(mem) < 1 << 60:
        out["memory"] = int(mem)
        used = _read(f"{root}/memory.current") or _read(f"{root}/memory/memory.usage_in_bytes")
        if used.isdigit():
            out["memory_used"] = int(used)
    quota, _, period = _read(f"{root}/cpu.max").partition(" ")
    if not quota:
        quota, period = _read(f"{root}/cpu/cpu.cfs_quota_us"), _read(f"{root}/cpu/cpu.cfs_period_us")
    if quota.lstrip("-").isdigit() and int(quota) > 0 and period.isdigit() and int(period) > 0:
        out["cpus"] = int(quota) / int(period)
    return out


def _raw() -> dict:
    proc = psutil.Process()
    with proc.oneshot():
        times = proc.cpu_times()
        mem = proc.memory_info()
        threads = proc.num_threads()
    net = psutil.net_io_counters()
    vm = psutil.virtual_memory()
    cpu = psutil.cpu_times()
    total = sum(cpu)
    return {
        "wall": time.monotonic(),
        "proc_cpu_s": times.user + times.system,
        "sys_total_s": total,
        "sys_busy_s": total - cpu.idle - getattr(cpu, "iowait", 0.0),
        "rss": mem.rss,
        "threads": threads,
        "net_sent": net.bytes_sent if net else 0,
        "net_recv": net.bytes_recv if net else 0,
        "mem_used": vm.total - vm.available,
        "mem_total": vm.total,
    }


def sample(now: float | None = None) -> list[dict]:
    """Measure (at most every MIN_INTERVAL seconds) and return the history, oldest first.

    Each entry: time (epoch s), app_cpu / sys_cpu (% of the CPUs the app may use), app_ram (bytes),
    threads, ram_used / ram_total (bytes; the container's limit when there is one), sent / recv (bytes/s)."""
    with _STATE["lock"]:
        last = _STATE["last"]
        if last is not None and time.monotonic() - last["wall"] < MIN_INTERVAL:
            return list(_STATE["history"])
        cur = _raw()
        _STATE["last"] = cur
        if last is None:
            return list(_STATE["history"])  # rates need two measurements
        limits = container_limits()
        cpus = limits.get("cpus") or psutil.cpu_count() or 1
        elapsed = max(cur["wall"] - last["wall"], 1e-6)
        pct = lambda used: max(0.0, min(100.0, 100 * used / elapsed / cpus))
        sys_total = cur["sys_total_s"] - last["sys_total_s"]
        entry = {
            "time": time.time() if now is None else now,
            "app_cpu": pct(cur["proc_cpu_s"] - last["proc_cpu_s"]),
            # In a container the machine's CPU belongs to the host and other tenants; not meaningful.
            "sys_cpu": (max(0.0, min(100.0, 100 * (cur["sys_busy_s"] - last["sys_busy_s"]) / sys_total))
                        if "cpus" not in limits and sys_total > 0 else None),
            "app_ram": cur["rss"],
            "threads": cur["threads"],
            "ram_used": limits.get("memory_used", cur["mem_used"]) if "memory" in limits else cur["mem_used"],
            "ram_total": limits.get("memory", cur["mem_total"]),
            "sent": max(0, cur["net_sent"] - last["net_sent"]) / elapsed,
            "recv": max(0, cur["net_recv"] - last["net_recv"]) / elapsed,
            "container": bool(limits),
        }
        _STATE["history"].append(entry)
        return list(_STATE["history"])


def totals() -> dict:
    """Bytes sent / received by this machine (or container) since it started."""
    net = psutil.net_io_counters()
    return {"sent": net.bytes_sent if net else 0, "recv": net.bytes_recv if net else 0}


def host() -> str:
    """Where the numbers come from, e.g. "Windows · 8 CPUs · 16.0 GB"."""
    limits = container_limits()
    cpus = limits.get("cpus") or psutil.cpu_count() or 1
    ram = limits.get("memory") or psutil.virtual_memory().total
    kind = "container" if limits else {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux")
    return f"{kind} · {cpus:g} CPUs · {format_bytes(ram)} · pid {os.getpid()}"


def format_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"
