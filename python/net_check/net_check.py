#!/usr/bin/env python3

import argparse
from contextlib import contextmanager
from importlib import import_module
import os
import platform
import re
import signal
import socket
import subprocess
import time
import urllib.request
from dataclasses import dataclass
import sys
from typing import Any, Optional
from urllib.parse import urlparse

HEADERS = {"User-Agent": "Mozilla/5.0"}
DEFAULT_SITES = [
    "https://www.baidu.com",
    "https://www.qq.com",
    "https://www.bing.com",
    "https://www.cloudflare.com",
    "https://www.wikipedia.org",
    "https://www.github.com",
    "https://www.google.com",
    "https://www.youtube.com",
]
PUBLIC_IP_APIS = [
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://checkip.amazonaws.com",
    "https://myip.ipip.net/",
]
PROXY_KEYS = [
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "no_proxy",
    "NO_PROXY",
]
PROXY_URL_KEYS = [
    "https_proxy",
    "HTTPS_PROXY",
    "http_proxy",
    "HTTP_PROXY",
    "all_proxy",
    "ALL_PROXY",
]


@dataclass
class FetchResult:
    status: str
    latency_ms: Optional[float]
    error_type: Optional[str] = None
    detail: Optional[str] = None
    status_code: Optional[int] = None
    final_url: Optional[str] = None


@dataclass
class ConnectivityResult:
    name: str
    label: str
    fetch: FetchResult


def build_opener(use_env_proxy):
    if use_env_proxy:
        return urllib.request.build_opener()
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


@contextmanager
def masked_proxy_env():
    saved = {}
    for key in PROXY_KEYS:
        saved[key] = os.environ.get(key)
        os.environ.pop(key, None)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def fetch_text(url, timeout=5, use_env_proxy=True):
    request = urllib.request.Request(url, headers=HEADERS)
    opener = build_opener(use_env_proxy)
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="ignore")
    except Exception:
        return None


def add_local_ipv4_candidate(ips, ip):
    if not isinstance(ip, str):
        return
    if ":" in ip:
        return
    if ip.startswith("127."):
        return
    ips.add(ip)


def get_routed_local_ip():
    # UDP connect picks the outbound interface address without sending traffic.
    for host in ("8.8.8.8", "1.1.1.1", "192.0.2.1"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect((host, 80))
                return sock.getsockname()[0]
        except OSError:
            continue
    return None


def get_local_ips():
    ips = set()
    hostname = socket.gethostname()

    try:
        for info in socket.getaddrinfo(hostname, None, family=socket.AF_INET):
            sockaddr = info[4]
            add_local_ipv4_candidate(ips, sockaddr[0])
    except Exception:
        pass

    routed_ip = get_routed_local_ip()
    add_local_ipv4_candidate(ips, routed_ip)

    return sorted(ips)


def is_valid_ipv4(ip):
    parts = ip.split(".")
    if len(parts) != 4:
        return False

    for part in parts:
        if not part.isdigit():
            return False
        value = int(part)
        if value < 0 or value > 255:
            return False

    return True


def extract_ip(text):
    if not text:
        return None

    stripped = text.strip()
    if is_valid_ipv4(stripped):
        return stripped

    matches = re.findall(r"(?:\d{1,3}\.){3}\d{1,3}", stripped)
    for ip in matches:
        if is_valid_ipv4(ip):
            return ip

    return None


def unique_preserve_order(items):
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def get_public_ips(use_env_proxy):
    ips = []
    for url in PUBLIC_IP_APIS:
        text = fetch_text(url, use_env_proxy=use_env_proxy)
        ip = extract_ip(text)
        if ip:
            ips.append(ip)
    return unique_preserve_order(ips)


def short_name(url):
    return urlparse(url).netloc.replace("www.", "")


def classify_error(exc):
    message = str(exc).lower()

    if isinstance(exc, TimeoutError) or "timed out" in message:
        return "timeout"
    if isinstance(exc, socket.gaierror):
        return "dns_error"
    if isinstance(exc, ConnectionRefusedError):
        return "connect_error"
    if isinstance(exc, OSError):
        if "getaddrinfo failed" in message or "name or service not known" in message:
            return "dns_error"
        if "proxy" in message:
            return "proxy_error"
        return "connect_error"
    if "proxy" in message:
        return "proxy_error"
    return "http_error"


def fetch_status(url, timeout, opener):
    request = urllib.request.Request(url, headers=HEADERS)
    start = time.perf_counter()

    try:
        with opener.open(request, timeout=timeout) as response:
            response.read(1)
            status_code = getattr(response, "status", None)
            final_url = getattr(response, "geturl", lambda: url)()

        latency_ms = (time.perf_counter() - start) * 1000
        if isinstance(status_code, int) and 200 <= status_code < 300:
            return FetchResult(
                status="ok",
                latency_ms=latency_ms,
                status_code=status_code,
                final_url=final_url,
            )
        if isinstance(status_code, int) and 300 <= status_code < 400:
            return FetchResult(
                status="redirect",
                latency_ms=latency_ms,
                status_code=status_code,
                final_url=final_url,
            )
        return FetchResult(
            status="http_error",
            latency_ms=latency_ms,
            error_type="HTTPStatus",
            detail="status={0}".format(status_code),
            status_code=status_code,
            final_url=final_url,
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        return FetchResult(
            status=classify_error(exc),
            latency_ms=latency_ms,
            error_type=exc.__class__.__name__,
            detail=str(exc),
        )


def run_connectivity_check(url, timeout, opener, label):
    return ConnectivityResult(
        name=short_name(url),
        label=label,
        fetch=fetch_status(url, timeout, opener),
    )


def format_connectivity_result(result):
    latency = result.fetch.latency_ms
    latency_text = "{0:.0f}ms".format(latency) if isinstance(latency, float) else "-"
    status = result.fetch.status

    if status in ("ok", "redirect"):
        code_text = "-"
        if isinstance(result.fetch.status_code, int):
            code_text = str(result.fetch.status_code)

        moved = ""
        if result.fetch.final_url:
            final_name = short_name(result.fetch.final_url)
            if final_name != result.name:
                moved = " -> {0}".format(final_name)

        return "{0:<13} {1:>7} {2:<3}{3}".format(status, latency_text, code_text, moved)

    return "{0:<13} {1:>7} {2:<3}".format(status, latency_text, "-")


def run_connectivity_checks(urls, timeout, opener, label):
    results = []
    ok_count = 0

    for url in urls:
        result = run_connectivity_check(url, timeout, opener, label)
        results.append(result)
        if result.fetch.status == "ok":
            ok_count += 1
        text = format_connectivity_result(result)
        print("{0:<18} {1}".format(result.name, text))

    return results, ok_count


def get_proxy_env():
    result = {}
    for key in PROXY_KEYS:
        value = os.environ.get(key)
        if value:
            result[key] = value
    return result


def pick_proxy_url(proxy_env):
    for key in PROXY_URL_KEYS:
        value = proxy_env.get(key)
        if value:
            return value
    return None


def parse_proxy_endpoint(proxy_url):
    candidate = proxy_url if "://" in proxy_url else "http://{0}".format(proxy_url)
    parsed = urlparse(candidate)
    return parsed.hostname, parsed.port


def check_tcp_endpoint(host, port, timeout):
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            latency_ms = (time.perf_counter() - start) * 1000
            return "reachable", latency_ms, None
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        return "unreachable", latency_ms, "{0}: {1}".format(exc.__class__.__name__, exc)


def bool_text(value):
    return "true" if bool(value) else "false"


def get_winreg_module() -> Optional[Any]:
    if platform.system() != "Windows":
        return None

    try:
        return import_module("winreg")
    except ImportError:
        return None


def get_windows_system_proxy():
    winreg = get_winreg_module()
    if winreg is None:
        return {}

    result = {}

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        )
        try:
            proxy_enable = read_registry_value(key, "ProxyEnable")
            proxy_server = read_registry_value(key, "ProxyServer")
            auto_config_url = read_registry_value(key, "AutoConfigURL")
            auto_detect = read_registry_value(key, "AutoDetect")

            if proxy_enable is not None:
                result["internet_settings.proxy_enable"] = bool_text(proxy_enable)
            if proxy_server:
                result["internet_settings.proxy_server"] = str(proxy_server)
            if auto_config_url:
                result["internet_settings.auto_config_url"] = str(auto_config_url)
            if auto_detect is not None:
                result["internet_settings.auto_detect"] = bool_text(auto_detect)
        finally:
            winreg.CloseKey(key)
    except Exception as exc:
        result["internet_settings.error"] = "{0}: {1}".format(
            exc.__class__.__name__, exc
        )

    try:
        completed = subprocess.run(
            ["netsh", "winhttp", "show", "proxy"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        output = (completed.stdout or completed.stderr).strip()
        if output:
            compact = " ".join(
                line.strip() for line in output.splitlines() if line.strip()
            )
            result["winhttp.proxy"] = compact
    except Exception as exc:
        result["winhttp.error"] = "{0}: {1}".format(exc.__class__.__name__, exc)

    return result


def read_registry_value(key, name):
    winreg = get_winreg_module()
    if winreg is None:
        return None

    try:
        value, _ = winreg.QueryValueEx(key, name)
        return value
    except OSError:
        return None


def print_key_value_section(title, values, key_width):
    print("\n[{0}]".format(title))
    if values:
        for key, value in values.items():
            print("{0:<{1}} {2}".format(key, key_width, value))
    else:
        print("none")


def print_list_section(title, items):
    print("\n[{0}]".format(title))
    if items:
        for item in items:
            print(item)
    else:
        print("unavailable")


def print_proxy_check(proxy_url, timeout):
    print("\n[proxy check]")
    if not proxy_url:
        print("none")
        return

    host, port = parse_proxy_endpoint(proxy_url)
    if not host or not port:
        print("proxy_url     {0}".format(proxy_url))
        print("proxy_tcp     invalid proxy url")
        return

    tcp_status, tcp_latency_ms, tcp_detail = check_tcp_endpoint(host, port, timeout)
    print("proxy_url     {0}".format(proxy_url))
    print("proxy_host    {0}".format(host))
    print("proxy_port    {0}".format(port))
    if tcp_status == "reachable":
        print("proxy_tcp     {0} ({1:.0f} ms)".format(tcp_status, tcp_latency_ms))
    else:
        print(
            "proxy_tcp     {0} ({1:.0f} ms) {2}".format(
                tcp_status, tcp_latency_ms, tcp_detail
            )
        )


def handle_sigint(signum, frame):
    raise SystemExit(130)


def main():
    signal.signal(signal.SIGINT, handle_sigint)
    parser = argparse.ArgumentParser(
        prog="net-check", description="Cross-platform network and proxy diagnostic tool"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="per-request timeout in seconds",
    )
    parser.add_argument(
        "--no-proxy-env",
        action="store_true",
        help="ignore current proxy-related environment variables for network tests",
    )
    args = parser.parse_args()

    @contextmanager
    def nullcontext():
        yield

    with masked_proxy_env() if args.no_proxy_env else nullcontext():
        print("[local]")
        local_ips = get_local_ips()
        if local_ips:
            for ip in local_ips:
                print(ip)
        else:
            print("unavailable")

        public_ips = get_public_ips(use_env_proxy=True)
        print_list_section("public", public_ips)

        proxy_env = get_proxy_env()
        print_key_value_section("proxy env", proxy_env, 12)

        proxy_url = pick_proxy_url(proxy_env)
        print_proxy_check(proxy_url, args.timeout)

        if platform.system() == "Windows":
            system_proxy = get_windows_system_proxy()
            print_key_value_section("windows system proxy", system_proxy, 32)

        print(
            "\n[connectivity] (no proxy env)"
            if args.no_proxy_env
            else "\n[connectivity]"
        )
        opener = build_opener(True)
        run_connectivity_checks(DEFAULT_SITES, args.timeout, opener, "")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit) as exc:
        if isinstance(exc, SystemExit) and exc.code != 130:
            raise
        sys.exit(130)
