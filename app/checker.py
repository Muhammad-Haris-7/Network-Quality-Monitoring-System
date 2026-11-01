import platform
import re
import subprocess
import time

import httpx


def check_http(url: str, timeout: float = 10.0) -> dict:
    """Visit a URL and measure status code and response time."""
    start = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url)
        latency = round((time.perf_counter() - start) * 1000, 1)
        ok = response.status_code < 400
        return {
            "is_up": ok,
            "status_code": response.status_code,
            "latency_ms": latency,
            "error": None if ok else f"HTTP {response.status_code}",
        }
    except httpx.TimeoutException:
        return {"is_up": False, "status_code": None, "latency_ms": None, "error": "Timed out"}
    except httpx.HTTPError as exc:
        return {
            "is_up": False,
            "status_code": None,
            "latency_ms": None,
            "error": f"Connection failed: {type(exc).__name__}",
        }
    except Exception as exc:  # invalid URL and other unexpected problems
        return {
            "is_up": False,
            "status_code": None,
            "latency_ms": None,
            "error": f"Check failed: {type(exc).__name__}",
        }


def check_ping(host: str, timeout_s: int = 3) -> dict:
    """Send one ping. The host was already validated, and no shell is used."""
    if platform.system().lower() == "windows":
        cmd = ["ping", "-n", "1", "-w", str(timeout_s * 1000), host]
    else:
        cmd = ["ping", "-c", "1", "-W", str(timeout_s), host]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s + 3)
    except FileNotFoundError:
        return {"is_up": False, "status_code": None, "latency_ms": None,
                "error": "ping command not available"}
    except subprocess.TimeoutExpired:
        return {"is_up": False, "status_code": None, "latency_ms": None, "error": "Ping timed out"}

    output = proc.stdout.lower()
    if proc.returncode == 0 and "ttl" in output:
        match = re.search(r"time[=<]\s*([\d.]+)\s*ms", output)
        latency = float(match.group(1)) if match else None
        return {"is_up": True, "status_code": None, "latency_ms": latency, "error": None}

    return {"is_up": False, "status_code": None, "latency_ms": None, "error": "No ping reply"}