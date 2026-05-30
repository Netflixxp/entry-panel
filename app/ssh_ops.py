from __future__ import annotations

import io
import posixpath
import time
from dataclasses import dataclass
from sqlite3 import Row

import paramiko

from app.rendering import RenderedConfig


@dataclass
class CommandResult:
    ok: bool
    log: str


def _connect(node: Row) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs = {
        "hostname": node["host"],
        "port": int(node["ssh_port"]),
        "username": node["ssh_user"],
        "timeout": 15,
        "banner_timeout": 20,
        "auth_timeout": 20,
    }
    if node["ssh_key_path"]:
        kwargs["key_filename"] = node["ssh_key_path"]
    if node["ssh_password"]:
        kwargs["password"] = node["ssh_password"]
    client.connect(**kwargs)
    return client


def _run(client: paramiko.SSHClient, command: str) -> tuple[int, str]:
    stdin, stdout, stderr = client.exec_command(command, get_pty=True, timeout=120)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    return stdout.channel.recv_exit_status(), out + err


def test_connection(node: Row) -> CommandResult:
    try:
        with _connect(node) as client:
            code, output = _run(client, "uname -a && nginx -v || true")
            return CommandResult(code == 0, output)
    except Exception as exc:  # noqa: BLE001
        return CommandResult(False, str(exc))


def test_target_from_node(node: Row, host: str, port: int) -> dict[str, object]:
    script = f"""
host='{host}'
port='{port}'
ip=$(getent ahostsv4 "$host" | awk '{{print $1; exit}}')
if [ -z "$ip" ]; then
  echo "OK=0"
  echo "IP=-"
  echo "LATENCY="
  echo "ERROR=resolve_failed"
  exit 0
fi
start=$(date +%s%3N)
if timeout 5 bash -c "</dev/tcp/$ip/$port" 2>/tmp/entry-panel-check.err; then
  end=$(date +%s%3N)
  echo "OK=1"
  echo "IP=$ip"
  echo "LATENCY=$((end-start))"
  echo "ERROR="
else
  err=$(cat /tmp/entry-panel-check.err 2>/dev/null)
  echo "OK=0"
  echo "IP=$ip"
  echo "LATENCY="
  echo "ERROR=${{err:-connect_failed}}"
fi
"""
    try:
        with _connect(node) as client:
            _, output = _run(client, script)
        values: dict[str, str] = {}
        for line in output.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
        return {
            "node_id": node["id"],
            "node_name": node["name"],
            "ok": values.get("OK") == "1",
            "ip": values.get("IP", "-"),
            "latency_ms": int(values["LATENCY"]) if values.get("LATENCY") else None,
            "error": values.get("ERROR", ""),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "node_id": node["id"],
            "node_name": node["name"],
            "ok": False,
            "ip": "-",
            "latency_ms": None,
            "error": str(exc),
        }


def collect_rule_traffic_from_node(node: Row, sni_domain: str) -> int:
    command = (
        "awk -v sni="
        + _shell_quote(sni_domain)
        + " '$4 == sni {sent += $9; received += $10} END {print sent + received + 0}' "
        + "/var/log/nginx/entry-panel-stream.log /var/log/nginx/entry-panel-stream.log.* 2>/dev/null || true"
    )
    try:
        with _connect(node) as client:
            _, output = _run(client, command)
        last_line = output.strip().splitlines()[-1] if output.strip() else "0"
        return int(float(last_line))
    except Exception:  # noqa: BLE001
        return 0


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def apply_config(node: Row, rendered: RenderedConfig, domain: str) -> CommandResult:
    log_parts: list[str] = []
    stamp = time.strftime("%Y%m%d%H%M%S")
    remote_root = f"/tmp/entry-panel-{stamp}"
    backup_dir = f"/etc/entry-panel/backups/{stamp}"
    try:
        with _connect(node) as client:
            sftp = client.open_sftp()
            _run(client, f"mkdir -p {remote_root}")
            _write_file(sftp, posixpath.join(remote_root, "nginx.conf"), rendered.nginx_conf)
            _write_file(sftp, posixpath.join(remote_root, "nginx-acme.conf"), rendered.acme_nginx_conf)
            _write_file(sftp, posixpath.join(remote_root, "index.html"), rendered.site_html)
            _write_file(sftp, posixpath.join(remote_root, "docs.html"), rendered.docs_html)
            _write_file(sftp, posixpath.join(remote_root, "downloads.html"), rendered.downloads_html)
            _write_file(sftp, posixpath.join(remote_root, "assets.html"), rendered.assets_html)
            _write_file(sftp, posixpath.join(remote_root, "about.html"), rendered.about_html)
            _write_file(sftp, posixpath.join(remote_root, "research.html"), rendered.research_html)
            _write_file(sftp, posixpath.join(remote_root, "markets.html"), rendered.markets_html)
            _write_file(sftp, posixpath.join(remote_root, "insights.html"), rendered.insights_html)
            _write_file(sftp, posixpath.join(remote_root, "contact.html"), rendered.contact_html)
            sftp.close()

            commands = [
                "apt-get update",
                "DEBIAN_FRONTEND=noninteractive apt-get install -y nginx libnginx-mod-stream certbot",
                "mkdir -p /var/www/entry-panel-site /var/www/entry-panel-acme/.well-known/acme-challenge /etc/entry-panel/backups",
                f"mkdir -p {backup_dir}",
                f"cp -a /etc/nginx/nginx.conf {backup_dir}/nginx.conf.bak 2>/dev/null || true",
                f"cp {remote_root}/index.html /var/www/entry-panel-site/index.html",
                "mkdir -p /var/www/entry-panel-site/docs /var/www/entry-panel-site/downloads /var/www/entry-panel-site/assets /var/www/entry-panel-site/about /var/www/entry-panel-site/research /var/www/entry-panel-site/markets /var/www/entry-panel-site/insights /var/www/entry-panel-site/contact",
                f"cp {remote_root}/docs.html /var/www/entry-panel-site/docs/index.html",
                f"cp {remote_root}/downloads.html /var/www/entry-panel-site/downloads/index.html",
                f"cp {remote_root}/assets.html /var/www/entry-panel-site/assets/index.html",
                f"cp {remote_root}/about.html /var/www/entry-panel-site/about/index.html",
                f"cp {remote_root}/research.html /var/www/entry-panel-site/research/index.html",
                f"cp {remote_root}/markets.html /var/www/entry-panel-site/markets/index.html",
                f"cp {remote_root}/insights.html /var/www/entry-panel-site/insights/index.html",
                f"cp {remote_root}/contact.html /var/www/entry-panel-site/contact/index.html",
                f"cp {remote_root}/nginx-acme.conf /etc/nginx/nginx.conf",
                "nginx -t",
                "systemctl reload nginx || systemctl restart nginx",
                f"certbot certonly --webroot -w /var/www/entry-panel-acme -d {domain} --agree-tos --register-unsafely-without-email --non-interactive",
                f"cp {remote_root}/nginx.conf /etc/nginx/nginx.conf",
                "nginx -t",
                "systemctl reload nginx || systemctl restart nginx",
            ]
            for command in commands:
                code, output = _run(client, command)
                log_parts.append(f"$ {command}\n{output}".strip())
                if code != 0:
                    _run(client, f"cp {backup_dir}/nginx.conf.bak /etc/nginx/nginx.conf 2>/dev/null || true")
                    _run(client, "nginx -t && (systemctl reload nginx || systemctl restart nginx) || true")
                    return CommandResult(False, "\n\n".join(log_parts))
            return CommandResult(True, "\n\n".join(log_parts))
    except Exception as exc:  # noqa: BLE001
        log_parts.append(str(exc))
        return CommandResult(False, "\n\n".join(log_parts))


def _write_file(sftp: paramiko.SFTPClient, path: str, content: str) -> None:
    with sftp.file(path, "w") as remote_file:
        remote_file.write(content)
