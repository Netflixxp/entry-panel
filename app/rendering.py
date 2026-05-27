from __future__ import annotations

import html
from dataclasses import dataclass
from sqlite3 import Row


@dataclass(frozen=True)
class RenderedConfig:
    nginx_conf: str
    acme_nginx_conf: str
    site_html: str
    docs_html: str
    downloads_html: str
    assets_html: str


def render_acme_nginx_conf(site: Row) -> str:
    domain = site["domain"]
    return f"""user www-data;
worker_processes auto;
pid /run/nginx.pid;
include /etc/nginx/modules-enabled/*.conf;

events {{
    worker_connections 1024;
}}

http {{
    sendfile on;
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    server {{
        listen 80;
        server_name {domain};
        root /var/www/entry-panel-site;

        location /.well-known/acme-challenge/ {{
            root /var/www/entry-panel-acme;
        }}

        location / {{
            try_files $uri $uri/ /index.html;
        }}
    }}
}}
"""


def render_nginx_conf(site: Row, rules: list[Row]) -> str:
    enabled_rules = [rule for rule in rules if int(rule["enabled"]) == 1]
    map_lines = [
        f"        {rule['sni_domain']} {rule['target_host']}:{int(rule['target_port'])};"
        for rule in enabled_rules
    ]
    map_body = "\n".join(map_lines) if map_lines else "        # No active SNI rules yet."
    domain = site["domain"]
    return f"""user www-data;
worker_processes auto;
pid /run/nginx.pid;
include /etc/nginx/modules-enabled/*.conf;

events {{
    worker_connections 1024;
}}

http {{
    sendfile on;
    tcp_nopush on;
    types_hash_max_size 2048;
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;

    server {{
        listen 80;
        server_name {domain};
        root /var/www/entry-panel-site;

        location /.well-known/acme-challenge/ {{
            root /var/www/entry-panel-acme;
        }}

        location / {{
            return 301 https://$host$request_uri;
        }}
    }}

    server {{
        listen 127.0.0.1:8443 ssl http2;
        server_name {domain};
        root /var/www/entry-panel-site;
        index index.html;

        ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;

        location / {{
            try_files $uri $uri/ /index.html;
        }}
    }}
}}

stream {{
    resolver 1.1.1.1 8.8.8.8 valid=300s ipv6=off;
    resolver_timeout 5s;

    map $ssl_preread_server_name $entry_panel_backend {{
{map_body}
        default 127.0.0.1:8443;
    }}

    log_format entry_panel_stream '$remote_addr [$time_local] '
                                  '$ssl_preread_server_name -> $entry_panel_backend '
                                  '$protocol $status $bytes_sent $bytes_received '
                                  '$session_time';
    access_log /var/log/nginx/entry-panel-stream.log entry_panel_stream;

    server {{
        listen 0.0.0.0:443;
        proxy_pass $entry_panel_backend;
        ssl_preread on;
        proxy_connect_timeout 5s;
        proxy_timeout 1h;
    }}
}}
"""


def render_site_html(site: Row, section: str = "home", preview: bool = False) -> str:
    site_name = html.escape(site["site_name"])
    tagline = html.escape(site["tagline"])
    domain = html.escape(site["domain"])
    nav_home = "/site/preview" if preview else "/"
    nav_docs = "/site/preview/docs" if preview else "/docs/"
    nav_downloads = "/site/preview/downloads" if preview else "/downloads/"
    nav_assets = "/site/preview/assets" if preview else "/assets/"
    back_link = '<a class="preview-back" href="/site">Back to panel</a>' if preview else ""
    active = {"home": "", "docs": "", "downloads": "", "assets": ""}
    active[section if section in active else "home"] = "active"
    pages = {
        "home": {
            "title": site_name,
            "eyebrow": "Global resource delivery",
            "intro": f"{tagline} Production-ready distribution for documentation bundles, binary packages, image assets, and static integration files.",
            "metric": "99.95%",
            "metric_label": "regional availability",
            "cards": [
                ("Docs", "Documentation Library", "Stable API references, mirror integration notes, and release manifest formats."),
                ("Releases", "Package Distribution", "Versioned archives indexed by platform, channel, checksum, and publish time."),
                ("Media", "Image Resources", "Optimized visual assets for product pages, technical documentation, and portals."),
            ],
            "extra": """
    <section class="section split">
      <div class="panel">
        <h2>Latest Release</h2>
        <div class="release-row"><span>resource-bundle</span><strong>4.8.2</strong><em>stable</em></div>
        <div class="release-row"><span>docs-snapshot</span><strong>2026.05</strong><em>current</em></div>
        <div class="release-row"><span>asset-pack</span><strong>2.14.0</strong><em>optimized</em></div>
      </div>
      <div class="panel">
        <h2>Operational Notes</h2>
        <p>All public artifacts are published with deterministic paths and checksum manifests. Static resources are cache-friendly and safe for automated retrieval.</p>
        <ul class="list compact">
          <li>Immutable release URLs</li>
          <li>Regional mirror validation</li>
          <li>Daily manifest refresh</li>
        </ul>
      </div>
    </section>""",
        },
        "docs": {
            "title": "Documentation",
            "eyebrow": "Technical reference",
            "intro": "Reference documents, integration guides, and versioned release notes for resource consumers. Each bundle is published as static HTML with a matching checksum manifest.",
            "metric": "v4.8",
            "metric_label": "current documentation snapshot",
            "cards": [
                ("Reference", "API Reference", "Stable endpoint descriptions, response examples, and manifest fields."),
                ("Operations", "Mirror Guide", "Cache refresh, checksum validation, DNS notes, and regional mirror practices."),
                ("History", "Release Notes", "Version history and compatibility notes for published bundles."),
            ],
            "extra": """
    <section class="section panel">
      <h2>Documentation Index</h2>
      <div class="search-box">Search documentation, manifests, integrations...</div>
      <table class="content-table">
        <tr><th>Document</th><th>Version</th><th>Status</th><th>Updated</th></tr>
        <tr><td>Resource Manifest Schema</td><td>4.8</td><td>Current</td><td>2026-05-24</td></tr>
        <tr><td>Mirror Integration Guide</td><td>3.9</td><td>Current</td><td>2026-05-20</td></tr>
        <tr><td>Static Asset Naming Policy</td><td>2.7</td><td>Maintained</td><td>2026-05-12</td></tr>
      </table>
    </section>""",
        },
        "downloads": {
            "title": "Downloads",
            "eyebrow": "Release catalog",
            "intro": "Release packages are grouped by platform and channel for predictable automated retrieval. Checksum manifests are refreshed alongside every published archive.",
            "metric": "428",
            "metric_label": "cached artifacts",
            "cards": [
                ("Stable", "Production Archive", "Recommended production artifacts with signed manifests."),
                ("LTS", "Extended Support", "Compatibility archives for long-lived deployments."),
                ("Verify", "Checksums", "SHA256 manifests for every downloadable package."),
            ],
            "extra": """
    <section class="section panel">
      <h2>Release Catalog</h2>
      <table class="content-table">
        <tr><th>Package</th><th>Channel</th><th>Size</th><th>Checksum</th></tr>
        <tr><td>resource-bundle-4.8.2.tar.gz</td><td>Stable</td><td>86 MB</td><td>SHA256</td></tr>
        <tr><td>docs-snapshot-2026.05.zip</td><td>Current</td><td>24 MB</td><td>SHA256</td></tr>
        <tr><td>asset-pack-2.14.0.avif.zip</td><td>Optimized</td><td>112 MB</td><td>SHA256</td></tr>
      </table>
    </section>""",
        },
        "assets": {
            "title": "Image Resources",
            "eyebrow": "Static asset library",
            "intro": "Static image resources are optimized for documentation, release portals, and integration pages. Assets are versioned by path for stable cache behavior.",
            "metric": "AVIF",
            "metric_label": "preferred image format",
            "cards": [
                ("Screens", "Screenshots", "Compressed UI images for documentation pages."),
                ("Systems", "Diagrams", "Versioned architecture and workflow diagrams."),
                ("UI", "Icons", "Small static assets for release portals."),
            ],
            "extra": """
    <section class="section panel">
      <h2>Asset Collections</h2>
      <div class="asset-grid">
        <div><span class="thumb a"></span><strong>Portal Screens</strong><p>UI snapshots for documentation pages.</p></div>
        <div><span class="thumb b"></span><strong>Architecture Diagrams</strong><p>Versioned network and resource flow diagrams.</p></div>
        <div><span class="thumb c"></span><strong>Release Icons</strong><p>Static interface assets for release portals.</p></div>
      </div>
    </section>""",
        },
    }
    page = pages.get(section, pages["home"])
    cards = "\n".join(
        f'      <div class="panel feature"><span class="kicker">{label}</span><strong>{title}</strong><p>{desc}</p></div>'
        for label, title, desc in page["cards"]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{site_name}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #14212f;
      --muted: #526173;
      --line: #d7e0ea;
      --panel: #ffffff;
      --wash: #f4f7fb;
      --accent: #0f6bb7;
      --accent-2: #13836f;
      --ok: #157347;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      color: var(--ink);
      background: var(--wash);
      line-height: 1.55;
    }}
    header {{
      background: #ffffff;
      border-bottom: 1px solid var(--line);
      position: sticky;
      top: 0;
      z-index: 5;
    }}
    .wrap {{ width: min(1120px, calc(100% - 32px)); margin: 0 auto; }}
    .nav {{ display: flex; align-items: center; justify-content: space-between; min-height: 64px; gap: 20px; }}
    .brand {{ font-weight: 700; font-size: 18px; display: flex; gap: 10px; align-items: center; }}
    .brand-mark {{ width: 28px; height: 28px; border-radius: 7px; background: linear-gradient(135deg, var(--accent), var(--accent-2)); display: inline-block; }}
    nav a {{ color: var(--muted); text-decoration: none; margin-left: 18px; font-size: 14px; padding: 8px 0; border-bottom: 2px solid transparent; }}
    nav a.active {{ color: var(--ink); border-bottom-color: var(--accent); }}
    main {{ padding: 42px 0; }}
    .hero {{ display: grid; grid-template-columns: 1.2fr .8fr; gap: 28px; align-items: stretch; }}
    h1 {{ font-size: clamp(32px, 5vw, 56px); line-height: 1.05; margin: 0 0 16px; letter-spacing: 0; }}
    h2 {{ margin: 0 0 14px; font-size: 22px; }}
    p {{ margin: 0 0 16px; color: var(--muted); }}
    .lede {{ font-size: 18px; color: #344457; }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 22px;
    }}
    .top-strip {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 24px; }}
    .top-strip div {{ border: 1px solid var(--line); background: #fff; border-radius: 8px; padding: 14px; }}
    .top-strip strong {{ display: block; font-size: 20px; }}
    .top-strip span {{ color: var(--muted); font-size: 13px; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 24px; }}
    .metric {{ font-size: 30px; font-weight: 700; color: var(--accent); }}
    .panel-label, .kicker {{ color: var(--accent-2); font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .08em; }}
    .feature strong {{ display: block; margin: 8px 0; font-size: 18px; }}
    .list {{ margin: 0; padding-left: 20px; color: var(--muted); }}
    .list.compact li {{ margin-bottom: 6px; }}
    .section {{ margin-top: 28px; }}
    .split {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    .hero-actions {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 22px; }}
    .primary-link, .secondary-link {{ min-height: 42px; display: inline-flex; align-items: center; padding: 9px 14px; border-radius: 6px; text-decoration: none; font-weight: 700; }}
    .primary-link {{ background: var(--accent); color: #fff; }}
    .secondary-link {{ border: 1px solid var(--line); color: var(--ink); background: #fff; }}
    .mini-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 14px; }}
    .mini-grid span {{ border: 1px solid var(--line); border-radius: 6px; padding: 9px; color: var(--muted); background: #f9fbfd; }}
    .mini-grid strong {{ color: var(--ok); float: right; }}
    .release-row {{ display: grid; grid-template-columns: 1fr auto auto; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--line); }}
    .release-row:last-child {{ border-bottom: 0; }}
    .release-row em {{ color: var(--accent-2); font-style: normal; }}
    .search-box {{ border: 1px solid var(--line); background: #fff; border-radius: 8px; padding: 13px 14px; color: var(--muted); margin-bottom: 14px; }}
    .content-table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
    .content-table th, .content-table td {{ text-align: left; border-bottom: 1px solid var(--line); padding: 12px 10px; }}
    .content-table th {{ color: var(--muted); font-size: 13px; }}
    .asset-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }}
    .asset-grid div {{ border: 1px solid var(--line); border-radius: 8px; padding: 14px; }}
    .thumb {{ display: block; min-height: 92px; margin-bottom: 12px; border-radius: 8px; background: linear-gradient(135deg, #dce9f6, #d8f0ea); border: 1px solid var(--line); }}
    .thumb.b {{ background: linear-gradient(135deg, #e8edf5, #d9e6fa); }}
    .thumb.c {{ background: linear-gradient(135deg, #e6f2ec, #eaf0f8); }}
    code {{ background: #edf2f7; padding: 2px 6px; border-radius: 4px; }}
    footer {{ border-top: 1px solid var(--line); padding: 22px 0; color: var(--muted); font-size: 13px; }}
    .preview-back {{
      position: fixed;
      right: 18px;
      bottom: 18px;
      z-index: 10;
      display: inline-flex;
      align-items: center;
      min-height: 42px;
      padding: 9px 14px;
      border-radius: 6px;
      background: #17202a;
      color: #fff;
      text-decoration: none;
      box-shadow: 0 8px 20px rgba(23, 32, 42, .18);
    }}
    @media (max-width: 820px) {{
      .hero, .grid, .split, .top-strip, .asset-grid {{ grid-template-columns: 1fr; }}
      .nav {{ align-items: flex-start; flex-direction: column; padding: 14px 0; }}
      nav a {{ margin: 0 14px 0 0; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="wrap nav">
      <div class="brand"><span class="brand-mark"></span>{site_name}</div>
      <nav>
        <a class="{active["home"]}" href="{nav_home}">Home</a>
        <a class="{active["docs"]}" href="{nav_docs}">Docs</a>
        <a class="{active["downloads"]}" href="{nav_downloads}">Downloads</a>
        <a class="{active["assets"]}" href="{nav_assets}">Assets</a>
      </nav>
    </div>
  </header>
  <main class="wrap">
    <section class="top-strip">
      <div><strong>18</strong><span>regional mirrors</span></div>
      <div><strong>428</strong><span>published artifacts</span></div>
      <div><strong>24h</strong><span>manifest refresh</span></div>
      <div><strong>TLS</strong><span>secure delivery</span></div>
    </section>
    <section class="hero">
      <div>
        <span class="panel-label">{page["eyebrow"]}</span>
        <h1>{page["title"]}</h1>
        <p class="lede">{page["intro"]}</p>
        <div class="hero-actions">
          <a class="primary-link" href="{nav_downloads}">View releases</a>
          <a class="secondary-link" href="{nav_docs}">Read documentation</a>
        </div>
      </div>
      <div class="panel">
        <div class="panel-label">Service indicator</div>
        <div class="metric">{page["metric"]}</div>
        <p>{page["metric_label"]}</p>
        <div class="mini-grid">
          <span>HK mirror <strong>online</strong></span>
          <span>JP mirror <strong>online</strong></span>
          <span>US mirror <strong>online</strong></span>
          <span>EU mirror <strong>online</strong></span>
        </div>
      </div>
    </section>
    <section class="grid section">
{cards}
    </section>
{page["extra"]}
    <section class="panel section">
      <strong>Service endpoint</strong>
      <p>Canonical host: <code>{domain}</code></p>
    </section>
  </main>
  <footer>
    <div class="wrap">Copyright (c) {site_name}. Static resource delivery service.</div>
  </footer>
{back_link}
</body>
</html>
"""


def render_all(site: Row, rules: list[Row]) -> RenderedConfig:
    return RenderedConfig(
        nginx_conf=render_nginx_conf(site, rules),
        acme_nginx_conf=render_acme_nginx_conf(site),
        site_html=render_site_html(site, "home"),
        docs_html=render_site_html(site, "docs"),
        downloads_html=render_site_html(site, "downloads"),
        assets_html=render_site_html(site, "assets"),
    )
