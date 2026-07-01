# net_check

Diagnose local network connectivity and proxy configuration.

This is a standalone script with no third-party Python dependencies.

It is designed for "why can/can't this machine reach the internet?" checks on
Windows and Linux, especially when proxy environment variables, Windows proxy
settings, VPNs, or split domestic/international connectivity may be involved.

## What it checks

`net_check.py` prints:

- local IPv4 addresses discovered from hostname lookup and outbound routing
- public IPv4 address candidates from several public IP services
- proxy-related environment variables
- TCP reachability of the selected proxy endpoint, if a proxy URL is configured
- Windows Internet Settings and WinHTTP proxy settings, on Windows
- HTTP connectivity to a mixed list of domestic and international sites

The connectivity checks report status, latency, HTTP status code, and redirect
target domain when relevant.

## Usage

```bash
python net_check.py
```

Ignore proxy-related environment variables while running the checks:

```bash
python net_check.py --no-proxy-env
```

Use a shorter per-request timeout:

```bash
python net_check.py --timeout 2
```

## CLI reference

```text
python net_check.py [options]
```

| Option | Default | Description |
| --- | --- | --- |
| `--timeout SECONDS` | `5` | Per-request timeout for public IP, proxy TCP, and HTTP checks. |
| `--no-proxy-env` | off | Temporarily remove proxy-related environment variables while collecting proxy and connectivity results. |

Use `-h` / `--help` for argparse's generated reference.

## Report sections

### `[local]`

Lists local non-loopback IPv4 addresses. The routed address is detected with a
UDP socket connect to common public routes; this chooses the outbound interface
without sending payload data.

### `[public]`

Queries several public IP services and prints unique IPv4 addresses in the order
they are found. Multiple values can indicate proxy/VPN differences, service
differences, or intermittent connectivity.

### `[proxy env]`

Prints currently configured proxy environment variables:

```text
http_proxy
https_proxy
all_proxy
HTTP_PROXY
HTTPS_PROXY
ALL_PROXY
no_proxy
NO_PROXY
```

### `[proxy check]`

Chooses the first configured proxy URL from:

```text
https_proxy, HTTPS_PROXY, http_proxy, HTTP_PROXY, all_proxy, ALL_PROXY
```

It then parses host/port and tests TCP reachability. This only checks whether
the proxy endpoint accepts a TCP connection; it does not authenticate with or
fully validate the proxy protocol.

### `[windows system proxy]`

On Windows, reads current-user Internet Settings from the registry and runs:

```powershell
netsh winhttp show proxy
```

This section is omitted on non-Windows systems.

### `[connectivity]`

Checks the default URL list:

```text
https://www.baidu.com
https://www.qq.com
https://www.bing.com
https://www.cloudflare.com
https://www.wikipedia.org
https://www.github.com
https://www.google.com
https://www.youtube.com
```

Each line has the form:

```text
site              status        latency code redirect
github.com        ok              420ms 200
youtube.com       timeout        5012ms -
```

Status values include:

- `ok`
- `redirect`
- `timeout`
- `dns_error`
- `connect_error`
- `proxy_error`
- `http_error`

## Proxy behavior

By default, Python's `urllib` uses proxy settings from the current environment.
That means connectivity results reflect the same proxy environment variables
many Python tools will see.

With `--no-proxy-env`, the script temporarily removes the proxy variables listed
above for the duration of the report. This is useful for comparing direct
network connectivity with proxied connectivity.

## Requirements

- Python 3.10 or newer
- no third-party Python packages

Windows proxy discovery additionally uses the standard-library `winreg` module
and the system `netsh` command.

## Limitations

- Public IP services and target websites are external services; temporary
  failures can affect results.
- HTTP checks download only a minimal response byte and are meant as diagnostics,
  not throughput tests.
- Proxy TCP reachability does not prove that the proxy credentials or rules allow
  a full HTTP request.
