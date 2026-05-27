from __future__ import annotations

import json
import secrets
import tempfile
import zipfile
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.db import DB_PATH, audit, execute, fetch_all, fetch_one, get_conn, init_db
from app.rendering import render_all, render_site_html
from app.security import hash_password, verify_password
from app.ssh_ops import apply_config, collect_rule_traffic_from_node, test_connection, test_target_from_node


BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="AnyTLS SNI Entry Panel")
app.add_middleware(SessionMiddleware, secret_key=secrets.token_hex(32))
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def status_label(value: str | None) -> str:
    labels = {
        "online": "在线",
        "unknown": "未知",
        "error": "异常",
        "checked": "已检测",
        "active": "运行中",
        "failed": "失败",
        "succeeded": "成功",
        "running": "执行中",
        "pending": "等待中",
    }
    return labels.get(value or "", value or "-")


templates.env.filters["status_label"] = status_label


def format_bytes(value: int | None) -> str:
    size = max(int(value or 0), 0)
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    amount = float(size)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.2f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{size} B"


templates.env.filters["format_bytes"] = format_bytes


def save_rule_check(rule_id: int, result: dict[str, object]) -> None:
    execute(
        """
        UPDATE sni_rules
        SET last_check_ok = ?, last_check_ip = ?, last_check_latency_ms = ?,
            last_check_error = ?, last_check_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            1 if result["ok"] else 0,
            str(result["ip"]),
            result["latency_ms"],
            str(result["error"]),
            rule_id,
        ),
    )


def _csv_cell(value: str) -> str:
    escaped = value.replace('"', '""')
    return f'"{escaped}"'


def _parse_rule_import(text: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("node_name,") or line.lower().startswith("sni_domain,"):
            continue
        parts = _split_import_line(line)
        if len(parts) >= 6:
            node_name, sni_domain, target_host, target_port, enabled, remark = parts[:6]
        elif len(parts) >= 4:
            node_name = ""
            sni_domain, target_host, target_port, remark = parts[:4]
            enabled = "1"
        elif len(parts) >= 3:
            node_name = ""
            sni_domain, target_host, target_port = parts[:3]
            enabled = "1"
            remark = ""
        else:
            continue
        items.append(
            {
                "node_name": node_name.strip(),
                "sni_domain": sni_domain.strip(),
                "target_host": target_host.strip(),
                "target_port": (target_port or "443").strip(),
                "enabled": "1" if str(enabled).strip().lower() not in {"0", "false", "off", "disabled"} else "0",
                "remark": remark.strip(),
            }
        )
    return [item for item in items if item["sni_domain"] and item["target_host"]]


def _split_import_line(line: str) -> list[str]:
    if "," in line:
        return _split_csv_line(line)
    return [part.strip() for part in line.replace("|", " ").split()]


def _split_csv_line(line: str) -> list[str]:
    values: list[str] = []
    current: list[str] = []
    in_quotes = False
    index = 0
    while index < len(line):
        char = line[index]
        if char == '"':
            if in_quotes and index + 1 < len(line) and line[index + 1] == '"':
                current.append('"')
                index += 1
            else:
                in_quotes = not in_quotes
        elif char == "," and not in_quotes:
            values.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1
    values.append("".join(current).strip())
    return values


def _resolve_import_node_id(node_name: str | None, fallback_node_id: int) -> int:
    if node_name:
        node = fetch_one("SELECT id FROM entry_nodes WHERE name = ? OR host = ?", (node_name, node_name))
        if node:
            return int(node["id"])
    return fallback_node_id


def apply_config_to_node(node_id: int) -> bool:
    node = fetch_one("SELECT * FROM entry_nodes WHERE id = ?", (node_id,))
    site = fetch_one("SELECT * FROM site_settings WHERE id = 1")
    if not node or not site:
        return False
    rules = fetch_all("SELECT * FROM sni_rules WHERE node_id = ? ORDER BY sni_domain", (node_id,))
    rendered = render_all(site, rules)
    version_id = execute(
        "INSERT INTO config_versions (node_id, version_label, config_text) VALUES (?, datetime('now'), ?)",
        (node_id, rendered.nginx_conf),
    )
    job_id = execute(
        "INSERT INTO apply_jobs (node_id, config_version_id, status, log) VALUES (?, ?, 'running', '')",
        (node_id, version_id),
    )
    result = apply_config(node, rendered, site["domain"])
    execute(
        "UPDATE apply_jobs SET status = ?, log = ?, finished_at = CURRENT_TIMESTAMP WHERE id = ?",
        ("succeeded" if result.ok else "failed", result.log, job_id),
    )
    execute(
        "UPDATE entry_nodes SET status = ?, nginx_status = ?, last_sync_at = CURRENT_TIMESTAMP, last_error = ? WHERE id = ?",
        ("online" if result.ok else "error", "active" if result.ok else "failed", None if result.ok else result.log[-1000:], node_id),
    )
    audit("node.apply", f"Applied config to node {node['name']}: {result.ok}")
    return result.ok


def auto_sync_rule_node(rule_id: int, reason: str) -> None:
    rule = fetch_one("SELECT node_id FROM sni_rules WHERE id = ?", (rule_id,))
    if rule and rule["node_id"]:
        apply_config_to_node(int(rule["node_id"]))
    audit("rules.auto_sync", reason)


@app.on_event("startup")
def startup() -> None:
    init_db()


def current_admin(request: Request) -> str:
    username = request.session.get("admin")
    if not username:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return str(username)


def redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


@app.get("/", response_class=HTMLResponse)
def home(request: Request, _: Annotated[str, Depends(current_admin)]) -> HTMLResponse:
    nodes = fetch_all("SELECT * FROM entry_nodes ORDER BY id DESC")
    rules = fetch_all("SELECT * FROM sni_rules ORDER BY sni_domain")
    jobs = fetch_all(
        """
        SELECT apply_jobs.*, entry_nodes.name AS node_name
        FROM apply_jobs
        JOIN entry_nodes ON entry_nodes.id = apply_jobs.node_id
        ORDER BY apply_jobs.id DESC LIMIT 8
        """
    )
    site = fetch_one("SELECT * FROM site_settings WHERE id = 1")
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "nodes": nodes, "rules": rules, "jobs": jobs, "site": site},
    )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(...), password: str = Form(...)) -> Response:
    admin = fetch_one("SELECT * FROM admins WHERE username = ?", (username,))
    if admin and verify_password(password, admin["password_hash"]):
        request.session["admin"] = username
        audit("login", f"{username} logged in")
        return redirect("/")
    return templates.TemplateResponse("login.html", {"request": request, "error": "用户名或密码错误"})


@app.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return redirect("/login")


@app.get("/entry-nodes", response_class=HTMLResponse)
def entry_nodes(request: Request, _: Annotated[str, Depends(current_admin)]) -> HTMLResponse:
    nodes = fetch_all("SELECT * FROM entry_nodes ORDER BY id DESC")
    return templates.TemplateResponse("entry_nodes.html", {"request": request, "nodes": nodes})


@app.get("/entry-nodes/new", response_class=HTMLResponse)
def new_entry_node(request: Request, _: Annotated[str, Depends(current_admin)]) -> HTMLResponse:
    return templates.TemplateResponse("entry_node_form.html", {"request": request, "node": None})


@app.post("/entry-nodes")
def create_entry_node(
    _: Annotated[str, Depends(current_admin)],
    name: str = Form(...),
    host: str = Form(...),
    ssh_port: int = Form(22),
    ssh_user: str = Form("root"),
    ssh_key_path: str = Form(""),
    ssh_password: str = Form(""),
) -> RedirectResponse:
    execute(
        """
        INSERT INTO entry_nodes (name, host, ssh_port, ssh_user, ssh_key_path, ssh_password)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (name, host, ssh_port, ssh_user, ssh_key_path.strip() or None, ssh_password or None),
    )
    audit("node.create", f"Created entry node {name} ({host})")
    return redirect("/entry-nodes")


@app.post("/entry-nodes/{node_id}/update")
def update_entry_node(
    node_id: int,
    _: Annotated[str, Depends(current_admin)],
    name: str = Form(...),
    host: str = Form(...),
    ssh_port: int = Form(22),
    ssh_user: str = Form("root"),
    ssh_key_path: str = Form(""),
    ssh_password: str = Form(""),
) -> RedirectResponse:
    node = fetch_one("SELECT * FROM entry_nodes WHERE id = ?", (node_id,))
    if not node:
        raise HTTPException(404)
    execute(
        """
        UPDATE entry_nodes
        SET name = ?, host = ?, ssh_port = ?, ssh_user = ?, ssh_key_path = ?, ssh_password = ?
        WHERE id = ?
        """,
        (name, host, ssh_port, ssh_user, ssh_key_path.strip() or None, ssh_password or None, node_id),
    )
    audit("node.update", f"Updated entry node {node_id}: {name} ({host})")
    return redirect(f"/entry-nodes/{node_id}")


@app.get("/entry-nodes/{node_id}", response_class=HTMLResponse)
def show_entry_node(request: Request, node_id: int, _: Annotated[str, Depends(current_admin)]) -> HTMLResponse:
    node = fetch_one("SELECT * FROM entry_nodes WHERE id = ?", (node_id,))
    if not node:
        raise HTTPException(404)
    versions = fetch_all("SELECT * FROM config_versions WHERE node_id = ? ORDER BY id DESC LIMIT 10", (node_id,))
    jobs = fetch_all("SELECT * FROM apply_jobs WHERE node_id = ? ORDER BY id DESC LIMIT 10", (node_id,))
    return templates.TemplateResponse(
        "entry_node_detail.html",
        {"request": request, "node": node, "versions": versions, "jobs": jobs},
    )


@app.post("/entry-nodes/{node_id}/test")
def test_entry_node(node_id: int, _: Annotated[str, Depends(current_admin)]) -> RedirectResponse:
    node = fetch_one("SELECT * FROM entry_nodes WHERE id = ?", (node_id,))
    if not node:
        raise HTTPException(404)
    result = test_connection(node)
    execute(
        "UPDATE entry_nodes SET status = ?, nginx_status = ?, last_error = ? WHERE id = ?",
        ("online" if result.ok else "error", "checked" if result.ok else "unknown", None if result.ok else result.log[-1000:], node_id),
    )
    audit("node.test", f"Tested node {node['name']}: {result.ok}")
    return redirect(f"/entry-nodes/{node_id}")


@app.post("/entry-nodes/{node_id}/delete")
def delete_entry_node(node_id: int, _: Annotated[str, Depends(current_admin)]) -> RedirectResponse:
    execute("DELETE FROM entry_nodes WHERE id = ?", (node_id,))
    audit("node.delete", f"Deleted node {node_id}")
    return redirect("/entry-nodes")


@app.post("/entry-nodes/{node_id}/apply")
def apply_entry_node(node_id: int, _: Annotated[str, Depends(current_admin)]) -> RedirectResponse:
    node = fetch_one("SELECT id FROM entry_nodes WHERE id = ?", (node_id,))
    if not node:
        raise HTTPException(404)
    apply_config_to_node(node_id)
    return redirect(f"/entry-nodes/{node_id}")


@app.get("/sni-rules", response_class=HTMLResponse)
def sni_rules(request: Request, _: Annotated[str, Depends(current_admin)]) -> HTMLResponse:
    keyword = request.query_params.get("q", "").strip()
    params: list[object] = []
    where = ""
    if keyword:
        like = f"%{keyword}%"
        where = """
        WHERE sni_rules.sni_domain LIKE ?
           OR sni_rules.target_host LIKE ?
           OR sni_rules.remark LIKE ?
           OR entry_nodes.name LIKE ?
           OR entry_nodes.host LIKE ?
        """
        params = [like, like, like, like, like]
    rules = fetch_all(
        f"""
        SELECT sni_rules.*, entry_nodes.name AS node_name, entry_nodes.host AS node_host
        FROM sni_rules
        LEFT JOIN entry_nodes ON entry_nodes.id = sni_rules.node_id
        {where}
        ORDER BY entry_nodes.name, sni_rules.sni_domain
        """,
        tuple(params),
    )
    nodes = fetch_all("SELECT * FROM entry_nodes ORDER BY name")
    check_rule_id = request.query_params.get("check_rule_id")
    check_result = fetch_one(
        """
        SELECT sni_rules.*, entry_nodes.name AS node_name, entry_nodes.host AS node_host
        FROM sni_rules
        LEFT JOIN entry_nodes ON entry_nodes.id = sni_rules.node_id
        WHERE sni_rules.id = ?
        """,
        (check_rule_id,),
    ) if check_rule_id else None
    return templates.TemplateResponse(
        "sni_rules.html",
        {"request": request, "rules": rules, "nodes": nodes, "check_result": check_result, "keyword": keyword},
    )


def _sni_rules_redirect(q: str = "") -> RedirectResponse:
    return redirect("/sni-rules" + (f"?{urlencode({'q': q})}" if q else ""))


@app.post("/sni-rules")
def create_sni_rule(
    _: Annotated[str, Depends(current_admin)],
    node_id: int = Form(...),
    sni_domain: str = Form(...),
    target_host: str = Form(...),
    target_port: int = Form(443),
    enabled: str | None = Form(None),
    remark: str = Form(""),
) -> RedirectResponse:
    rule_id = execute(
        "INSERT INTO sni_rules (node_id, sni_domain, target_host, target_port, enabled, remark) VALUES (?, ?, ?, ?, ?, ?)",
        (node_id, sni_domain.strip(), target_host.strip(), target_port, 1 if enabled else 0, remark.strip() or None),
    )
    audit("rule.create", f"Created SNI rule {sni_domain} -> {target_host}:{target_port}")
    auto_sync_rule_node(rule_id, f"Auto synced after creating SNI rule {sni_domain}")
    return _sni_rules_redirect()


@app.get("/sni-rules/export")
def export_sni_rules(_: Annotated[str, Depends(current_admin)], q: str = "") -> PlainTextResponse:
    keyword = q.strip()
    params: list[object] = []
    where = ""
    if keyword:
        like = f"%{keyword}%"
        where = """
        WHERE sni_rules.sni_domain LIKE ?
           OR sni_rules.target_host LIKE ?
           OR sni_rules.remark LIKE ?
           OR entry_nodes.name LIKE ?
           OR entry_nodes.host LIKE ?
        """
        params = [like, like, like, like, like]
    rules = fetch_all(
        f"""
        SELECT sni_rules.*, entry_nodes.name AS node_name
        FROM sni_rules
        LEFT JOIN entry_nodes ON entry_nodes.id = sni_rules.node_id
        {where}
        ORDER BY entry_nodes.name, sni_rules.sni_domain
        """,
        tuple(params),
    )
    lines = ["node_name,sni_domain,target_host,target_port,enabled,remark"]
    for rule in rules:
        values = [
            rule["node_name"] or "",
            rule["sni_domain"],
            rule["target_host"],
            str(rule["target_port"]),
            "1" if rule["enabled"] else "0",
            rule["remark"] or "",
        ]
        lines.append(",".join(_csv_cell(value) for value in values))
    return PlainTextResponse(
        "\n".join(lines) + "\n",
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sni-rules.csv"},
    )


@app.post("/sni-rules/import")
async def import_sni_rules(
    _: Annotated[str, Depends(current_admin)],
    node_id: int = Form(...),
    rules_text: str = Form(""),
    file: UploadFile | None = File(None),
) -> RedirectResponse:
    text = rules_text.strip()
    if file and file.filename:
        text = (await file.read()).decode("utf-8-sig", errors="replace")
    imported = 0
    touched_nodes = {node_id}
    for item in _parse_rule_import(text):
        row_node_id = _resolve_import_node_id(item.get("node_name"), node_id)
        touched_nodes.add(row_node_id)
        execute(
            """
            INSERT INTO sni_rules (node_id, sni_domain, target_host, target_port, enabled, remark)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(sni_domain) DO UPDATE SET
                node_id = excluded.node_id,
                target_host = excluded.target_host,
                target_port = excluded.target_port,
                enabled = excluded.enabled,
                remark = excluded.remark
            """,
            (
                row_node_id,
                item["sni_domain"],
                item["target_host"],
                int(item.get("target_port") or 443),
                int(item.get("enabled") if item.get("enabled") is not None else 1),
                item.get("remark") or None,
            ),
        )
        imported += 1
    for touched_node_id in touched_nodes:
        apply_config_to_node(int(touched_node_id))
    audit("rule.import", f"Imported {imported} SNI rules")
    return _sni_rules_redirect()


@app.post("/sni-rules/bulk-switch-node")
def bulk_switch_sni_rule_node(
    _: Annotated[str, Depends(current_admin)],
    from_node_id: int = Form(...),
    to_node_id: int = Form(...),
    q: str = Form(""),
) -> RedirectResponse:
    keyword = q.strip()
    params: list[object] = [to_node_id, from_node_id]
    where = "node_id = ?"
    if keyword:
        like = f"%{keyword}%"
        where += " AND (sni_domain LIKE ? OR target_host LIKE ? OR remark LIKE ?)"
        params.extend([like, like, like])
    execute(f"UPDATE sni_rules SET node_id = ? WHERE {where}", tuple(params))
    apply_config_to_node(from_node_id)
    apply_config_to_node(to_node_id)
    audit("rule.bulk_switch_node", f"Moved rules from node {from_node_id} to {to_node_id}")
    return _sni_rules_redirect(keyword)


@app.post("/sni-rules/{rule_id}/update")
def update_sni_rule(
    rule_id: int,
    _: Annotated[str, Depends(current_admin)],
    node_id: int = Form(...),
    sni_domain: str = Form(...),
    target_host: str = Form(...),
    target_port: int = Form(443),
    enabled: str | None = Form(None),
    remark: str = Form(""),
) -> RedirectResponse:
    rule = fetch_one("SELECT * FROM sni_rules WHERE id = ?", (rule_id,))
    if not rule:
        raise HTTPException(404)
    execute(
        """
        UPDATE sni_rules
        SET node_id = ?, sni_domain = ?, target_host = ?, target_port = ?, enabled = ?, remark = ?
        WHERE id = ?
        """,
        (node_id, sni_domain.strip(), target_host.strip(), target_port, 1 if enabled else 0, remark.strip() or None, rule_id),
    )
    audit("rule.update", f"Updated SNI rule {rule_id}: {sni_domain} -> {target_host}:{target_port}")
    if rule["node_id"] and int(rule["node_id"]) != node_id:
        apply_config_to_node(int(rule["node_id"]))
    auto_sync_rule_node(rule_id, f"Auto synced after updating SNI rule {sni_domain}")
    return redirect("/sni-rules")


@app.post("/sni-rules/{rule_id}/check")
def check_sni_rule(rule_id: int, _: Annotated[str, Depends(current_admin)]) -> RedirectResponse:
    rule = fetch_one("SELECT * FROM sni_rules WHERE id = ?", (rule_id,))
    if not rule:
        raise HTTPException(404)
    node = fetch_one("SELECT * FROM entry_nodes WHERE id = ?", (rule["node_id"],)) if rule["node_id"] else None
    if not node:
        result = {"ok": False, "ip": "-", "latency_ms": None, "error": "没有入口机"}
    else:
        result = test_target_from_node(node, rule["target_host"], int(rule["target_port"]))
        if result["ok"]:
            result["error"] = f"{result['node_name']} -> 落地"
    save_rule_check(rule_id, result)
    audit("rule.check", f"Checked SNI rule {rule_id}: {result}")
    return redirect(f"/sni-rules?check_rule_id={rule_id}")


@app.post("/sni-rules/{rule_id}/traffic")
def refresh_rule_traffic(rule_id: int, _: Annotated[str, Depends(current_admin)]) -> RedirectResponse:
    rule = fetch_one("SELECT * FROM sni_rules WHERE id = ?", (rule_id,))
    if not rule:
        raise HTTPException(404)
    node = fetch_one("SELECT * FROM entry_nodes WHERE id = ?", (rule["node_id"],)) if rule["node_id"] else None
    if node:
        total = collect_rule_traffic_from_node(node, rule["sni_domain"])
        execute("UPDATE sni_rules SET traffic_bytes = ? WHERE id = ?", (total, rule_id))
        audit("rule.traffic", f"Refreshed traffic for rule {rule_id}: {total}")
    return redirect("/sni-rules")


@app.post("/sni-rules/{rule_id}/traffic/clear")
def clear_rule_traffic(rule_id: int, _: Annotated[str, Depends(current_admin)]) -> RedirectResponse:
    rule = fetch_one("SELECT * FROM sni_rules WHERE id = ?", (rule_id,))
    if not rule:
        raise HTTPException(404)
    node = fetch_one("SELECT * FROM entry_nodes WHERE id = ?", (rule["node_id"],)) if rule["node_id"] else None
    current = collect_rule_traffic_from_node(node, rule["sni_domain"]) if node else int(rule["traffic_bytes"] or 0)
    execute(
        "UPDATE sni_rules SET traffic_bytes = ?, traffic_offset_bytes = ? WHERE id = ?",
        (current, current, rule_id),
    )
    audit("rule.traffic.clear", f"Cleared traffic counter for rule {rule_id}")
    return redirect("/sni-rules")


@app.post("/sni-rules/{rule_id}/delete")
def delete_sni_rule(rule_id: int, _: Annotated[str, Depends(current_admin)]) -> RedirectResponse:
    rule = fetch_one("SELECT * FROM sni_rules WHERE id = ?", (rule_id,))
    execute("DELETE FROM sni_rules WHERE id = ?", (rule_id,))
    audit("rule.delete", f"Deleted SNI rule {rule_id}")
    if rule and rule["node_id"]:
        apply_config_to_node(int(rule["node_id"]))
    audit("rules.auto_sync", f"Auto synced after deleting SNI rule {rule_id}")
    return redirect("/sni-rules")


@app.post("/sni-rules/{rule_id}/toggle")
def toggle_sni_rule(rule_id: int, _: Annotated[str, Depends(current_admin)]) -> RedirectResponse:
    execute("UPDATE sni_rules SET enabled = CASE enabled WHEN 1 THEN 0 ELSE 1 END WHERE id = ?", (rule_id,))
    audit("rule.toggle", f"Toggled SNI rule {rule_id}")
    auto_sync_rule_node(rule_id, f"Auto synced after toggling SNI rule {rule_id}")
    return redirect("/sni-rules")


@app.get("/site", response_class=HTMLResponse)
def site_page(request: Request, _: Annotated[str, Depends(current_admin)]) -> HTMLResponse:
    site = fetch_one("SELECT * FROM site_settings WHERE id = 1")
    return templates.TemplateResponse("site.html", {"request": request, "site": site})


@app.get("/site/preview", response_class=HTMLResponse)
def site_preview(_: Annotated[str, Depends(current_admin)]) -> HTMLResponse:
    site = fetch_one("SELECT * FROM site_settings WHERE id = 1")
    if not site:
        raise HTTPException(404)
    return HTMLResponse(render_site_html(site, "home", preview=True))


@app.get("/site/preview/docs", response_class=HTMLResponse)
def site_preview_docs(_: Annotated[str, Depends(current_admin)]) -> HTMLResponse:
    site = fetch_one("SELECT * FROM site_settings WHERE id = 1")
    if not site:
        raise HTTPException(404)
    return HTMLResponse(render_site_html(site, "docs", preview=True))


@app.get("/site/preview/downloads", response_class=HTMLResponse)
def site_preview_downloads(_: Annotated[str, Depends(current_admin)]) -> HTMLResponse:
    site = fetch_one("SELECT * FROM site_settings WHERE id = 1")
    if not site:
        raise HTTPException(404)
    return HTMLResponse(render_site_html(site, "downloads", preview=True))


@app.get("/site/preview/assets", response_class=HTMLResponse)
def site_preview_assets(_: Annotated[str, Depends(current_admin)]) -> HTMLResponse:
    site = fetch_one("SELECT * FROM site_settings WHERE id = 1")
    if not site:
        raise HTTPException(404)
    return HTMLResponse(render_site_html(site, "assets", preview=True))


@app.post("/site")
def update_site(
    _: Annotated[str, Depends(current_admin)],
    domain: str = Form(...),
    site_name: str = Form(...),
    tagline: str = Form(...),
) -> RedirectResponse:
    execute(
        "UPDATE site_settings SET domain = ?, site_name = ?, tagline = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
        (domain.strip(), site_name.strip(), tagline.strip()),
    )
    audit("site.update", f"Updated site domain to {domain}")
    return redirect("/site")


@app.get("/backups", response_class=HTMLResponse)
def backups_page(request: Request, _: Annotated[str, Depends(current_admin)]) -> HTMLResponse:
    return templates.TemplateResponse("backups.html", {"request": request})


@app.get("/backups/export")
def export_backup(_: Annotated[str, Depends(current_admin)]) -> StreamingResponse:
    payload = {}
    with get_conn() as conn:
        for table in ["entry_nodes", "sni_rules", "site_settings"]:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            payload[table] = [dict(row) for row in rows]
    tmp = tempfile.TemporaryFile()
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("backup.json", json.dumps(payload, ensure_ascii=False, indent=2))
        zf.writestr("README.txt", "SSH passwords are included only if they were stored in the panel database.\n")
    tmp.seek(0)
    return StreamingResponse(
        tmp,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=entry-panel-backup.zip"},
    )


@app.post("/backups/import")
async def import_backup(
    _: Annotated[str, Depends(current_admin)],
    file: UploadFile = File(...),
) -> RedirectResponse:
    content = await file.read()
    with tempfile.TemporaryDirectory() as td:
        zip_path = Path(td) / "backup.zip"
        zip_path.write_bytes(content)
        with zipfile.ZipFile(zip_path) as zf:
            payload = json.loads(zf.read("backup.json").decode("utf-8"))
    with get_conn() as conn:
        conn.execute("DELETE FROM sni_rules")
        conn.execute("DELETE FROM entry_nodes")
        site_rows = payload.get("site_settings", [])
        if site_rows:
            site = site_rows[0]
            conn.execute(
                "UPDATE site_settings SET domain = ?, site_name = ?, tagline = ? WHERE id = 1",
                (site["domain"], site["site_name"], site["tagline"]),
            )
        for node in payload.get("entry_nodes", []):
            conn.execute(
                """
                INSERT INTO entry_nodes (name, host, ssh_port, ssh_user, ssh_key_path, ssh_password, status, nginx_status, last_error)
                VALUES (?, ?, ?, ?, ?, ?, 'unknown', 'unknown', NULL)
                """,
                (node["name"], node["host"], node["ssh_port"], node["ssh_user"], node.get("ssh_key_path"), node.get("ssh_password")),
            )
        for rule in payload.get("sni_rules", []):
            conn.execute(
                "INSERT INTO sni_rules (sni_domain, target_host, target_port, enabled, remark) VALUES (?, ?, ?, ?, ?)",
                (rule["sni_domain"], rule["target_host"], rule["target_port"], rule["enabled"], rule.get("remark")),
            )
    audit("backup.import", f"Imported backup {file.filename}")
    return redirect("/backups")


@app.post("/admin/password")
def change_password(
    request: Request,
    _: Annotated[str, Depends(current_admin)],
    current_password: str = Form(...),
    new_password: str = Form(...),
) -> RedirectResponse:
    username = request.session["admin"]
    admin = fetch_one("SELECT * FROM admins WHERE username = ?", (username,))
    if not admin or not verify_password(current_password, admin["password_hash"]):
        return redirect("/")
    execute("UPDATE admins SET password_hash = ? WHERE username = ?", (hash_password(new_password), username))
    audit("admin.password", f"Changed password for {username}")
    return redirect("/")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
