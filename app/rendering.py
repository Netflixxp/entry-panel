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
    about_html: str
    research_html: str
    markets_html: str
    insights_html: str
    contact_html: str


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
    nav_about = "/site/preview/about" if preview else "/about/"
    nav_research = "/site/preview/research" if preview else "/research/"
    nav_markets = "/site/preview/markets" if preview else "/markets/"
    nav_insights = "/site/preview/insights" if preview else "/insights/"
    nav_contact = "/site/preview/contact" if preview else "/contact/"
    back_link = '<a class="preview-back" href="/site">Back to panel</a>' if preview else ""
    chart_svg = """<svg viewBox="0 0 640 180" role="img" aria-label="Regional infrastructure chart">
      <rect width="640" height="180" fill="#f6f8fb"/>
      <path d="M0 138 L70 124 L140 130 L210 92 L280 104 L350 68 L420 76 L490 48 L560 58 L640 30 L640 180 L0 180 Z" fill="#d8e7ef"/>
      <path d="M0 138 L70 124 L140 130 L210 92 L280 104 L350 68 L420 76 L490 48 L560 58 L640 30" fill="none" stroke="#1c6b72" stroke-width="5"/>
      <g fill="#b48a3c"><circle cx="210" cy="92" r="7"/><circle cx="350" cy="68" r="7"/><circle cx="490" cy="48" r="7"/><circle cx="640" cy="30" r="7"/></g>
      <g fill="#617081" font-size="18" font-family="Arial"><text x="28" y="36">Availability Index</text><text x="470" y="158">Q2 2026</text></g>
    </svg>"""
    network_svg = """<svg viewBox="0 0 640 180" role="img" aria-label="Network delivery diagram">
      <rect width="640" height="180" fill="#f6f8fb"/>
      <g stroke="#9fb4c3" stroke-width="3" fill="none"><path d="M120 92 C220 20 330 20 430 92"/><path d="M120 92 C230 160 330 160 430 92"/><path d="M430 92 L540 52"/><path d="M430 92 L540 132"/></g>
      <g fill="#0f2436"><circle cx="120" cy="92" r="28"/><circle cx="430" cy="92" r="28"/><circle cx="540" cy="52" r="22"/><circle cx="540" cy="132" r="22"/></g>
      <g fill="#b48a3c"><circle cx="120" cy="92" r="10"/><circle cx="430" cy="92" r="10"/><circle cx="540" cy="52" r="8"/><circle cx="540" cy="132" r="8"/></g>
      <g fill="#617081" font-size="17" font-family="Arial"><text x="36" y="38">Resource Flow</text><text x="450" y="164">Mirror Nodes</text></g>
    </svg>"""
    media_svg = """<svg viewBox="0 0 640 180" role="img" aria-label="Publication media preview">
      <rect width="640" height="180" fill="#f8f4ec"/>
      <rect x="36" y="30" width="168" height="112" fill="#ffffff" stroke="#d8e0e9"/>
      <rect x="236" y="30" width="168" height="112" fill="#ffffff" stroke="#d8e0e9"/>
      <rect x="436" y="30" width="168" height="112" fill="#ffffff" stroke="#d8e0e9"/>
      <path d="M58 116 L92 82 L126 104 L162 64 L184 116 Z" fill="#d8e7ef"/>
      <path d="M258 118 H382 M258 88 H362 M258 58 H334" stroke="#1c6b72" stroke-width="8"/>
      <circle cx="500" cy="86" r="38" fill="#d8e7ef"/><path d="M500 48 A38 38 0 0 1 538 86 L500 86 Z" fill="#b48a3c"/>
      <g fill="#617081" font-size="17" font-family="Arial"><text x="36" y="164">Report Media Pack</text></g>
    </svg>"""
    active = {
        "home": "",
        "about": "",
        "research": "",
        "markets": "",
        "insights": "",
        "docs": "",
        "downloads": "",
        "assets": "",
        "contact": "",
    }
    active[section if section in active else "home"] = "active"
    pages = {
        "home": {
            "eyebrow": "Institutional data infrastructure",
            "title": "Global intelligence for resilient digital markets.",
            "intro": f"{tagline} {site_name} operates research-grade data delivery, market documentation, and verified resource distribution for enterprise teams.",
            "metric": "$4.8B",
            "metric_label": "tracked digital infrastructure exposure",
            "cards": [
                ("Research", "Market Intelligence", "Regional data, release notes, and infrastructure briefs prepared for operations and strategy teams."),
                ("Infrastructure", "Verified Distribution", "Stable delivery endpoints for documentation, release bundles, manifests, and media resources."),
                ("Operations", "Continuity Services", "Availability monitoring, mirror validation, and structured resource lifecycle management."),
            ],
            "extra": """
    <section class="section editorial">
      <div>
        <span class="panel-label">What we monitor</span>
        <h2>Data centers, networks, and operational capacity.</h2>
        <p>Our coverage focuses on digital infrastructure assets, enterprise software delivery channels, regional connectivity, and the operational signals that support long-term planning.</p>
      </div>
      <div class="insight-list">
        <article><strong>Q2 Infrastructure Brief</strong><span>Capacity expansion across North America and Asia-Pacific.</span></article>
        <article><strong>Mirror Reliability Notes</strong><span>Operational indicators for public and private resource distribution.</span></article>
        <article><strong>Data Delivery Index</strong><span>Weekly movement in latency, availability, and release integrity.</span></article>
      </div>
    </section>
    <section class="section panel">
      <span class="panel-label">Company profile</span>
      <h2>Built for research, operations, and dependable publication.</h2>
      <p>Our team maintains a structured resource center for organizations that rely on consistent access to market notes, data infrastructure briefs, release packages, and supporting media. The site is organized around long-lived content, predictable publication schedules, and direct access to verified resources.</p>
      <div class="profile-grid">
        <div><strong>Research Coverage</strong><span>Digital infrastructure, data center operations, cloud delivery, and enterprise software distribution.</span></div>
        <div><strong>Publication Controls</strong><span>Versioned documents, checksum manifests, release retention, and controlled update windows.</span></div>
        <div><strong>Regional Operations</strong><span>Coverage notes across North America, Europe, and Asia-Pacific business regions.</span></div>
        <div><strong>Resource Continuity</strong><span>Mirror validation, static delivery reviews, and availability reporting for published assets.</span></div>
      </div>
    </section>
    <section class="section split">
      <div class="panel quiet">
        <h2>Operating Principles</h2>
        <p>We publish deterministic resource paths, checksum-backed release catalogs, and long-lived documentation snapshots for teams that need predictable access over time.</p>
      </div>
      <div class="panel quiet">
        <h2>Coverage Areas</h2>
        <p>Digital infrastructure, data distribution, cloud delivery operations, research portals, and resource availability across major business regions.</p>
      </div>
    </section>
    <section class="section panel">
      <span class="panel-label">Latest insights</span>
      <h2>Recent research notes</h2>
      <div class="news-grid">
        <article><strong>Enterprise delivery channels remain focused on verified static assets</strong><p>Operations teams continue to prefer simple, verifiable release paths for critical documents and resource bundles.</p><span>May 2026</span></article>
        <article><strong>Regional infrastructure planning shifts toward resilient access points</strong><p>Organizations are reviewing resource availability across market regions as infrastructure demand remains elevated.</p><span>May 2026</span></article>
        <article><strong>Checksum-backed archives reduce support friction</strong><p>Maintained manifest files provide a practical audit trail for downstream publication workflows.</p><span>April 2026</span></article>
      </div>
    </section>
    <section class="section contact-band">
      <div>
        <span class="panel-label">Contact</span>
        <h2>Resource and publication inquiries</h2>
        <p>For documentation access, archive questions, or regional publication notes, contact the resource coordination desk.</p>
      </div>
      <div>
        <p><strong>Email</strong><br>research@globalresource.example</p>
        <p><strong>Office</strong><br>1200 Market Street, Suite 410<br>New York, NY 10005</p>
      </div>
    </section>""",
        },
        "about": {
            "eyebrow": "About the firm",
            "title": "Independent research operations for digital infrastructure markets.",
            "intro": f"{site_name} maintains a public resource center for market intelligence, infrastructure reporting, release archives, and verified static publication workflows.",
            "metric": "2018",
            "metric_label": "research operations established",
            "cards": [
                ("Mandate", "Infrastructure Coverage", "We track data centers, enterprise software delivery, network availability, and supporting resource operations."),
                ("Process", "Publication Discipline", "Research notes and resource packages are organized with version identifiers, review records, and retention windows."),
                ("Audience", "Enterprise Readers", "The library is structured for analysts, infrastructure managers, procurement teams, and continuity planners."),
            ],
            "extra": """
    <section class="section panel">
      <span class="panel-label">Operating profile</span>
      <h2>Built around stable public information and repeatable publication controls.</h2>
      <p>The resource center combines long-lived reference pages, monthly research summaries, and static asset archives. Each area is designed to remain readable without interactive dashboards, account systems, or short-lived application state.</p>
      <div class="profile-grid">
        <div><strong>Research Desk</strong><span>Maintains market summaries, regional infrastructure notes, and publication calendars.</span></div>
        <div><strong>Data Operations</strong><span>Reviews public indicators, availability reports, and archive integrity records.</span></div>
        <div><strong>Publication Team</strong><span>Prepares documents, release manifests, charts, and web-ready resource bundles.</span></div>
        <div><strong>Continuity Review</strong><span>Checks access paths, static delivery health, and documented update procedures.</span></div>
      </div>
    </section>
    <section class="section split">
      <div class="panel quiet">
        <h2>Governance</h2>
        <p>Editorial updates follow a lightweight control model: source review, publication approval, version assignment, archive retention, and periodic refresh.</p>
      </div>
      <div class="panel quiet">
        <h2>Coverage Boundaries</h2>
        <p>We focus on observable infrastructure, public market signals, resource delivery practices, and documentation systems used by operational teams.</p>
      </div>
    </section>
    <section class="section panel">
      <h2>Company Milestones</h2>
      <table class="content-table">
        <tr><th>Year</th><th>Milestone</th><th>Focus</th></tr>
        <tr><td>2018</td><td>Research operations launched</td><td>Digital infrastructure tracking</td></tr>
        <tr><td>2021</td><td>Static publication archive introduced</td><td>Document retention and release integrity</td></tr>
        <tr><td>2024</td><td>Regional availability reporting expanded</td><td>Americas, Europe, Asia-Pacific</td></tr>
        <tr><td>2026</td><td>Resource center consolidated</td><td>Research, downloads, media, documentation</td></tr>
      </table>
    </section>""",
        },
        "research": {
            "eyebrow": "Research platform",
            "title": "Market research shaped for infrastructure and operations teams.",
            "intro": "Research pages combine recurring market briefs, methodology notes, and regional observations for teams that need a stable public reference.",
            "metric": "52",
            "metric_label": "scheduled research releases per year",
            "cards": [
                ("Briefs", "Quarterly Market Review", "Coverage of data center investment, network capacity, and enterprise delivery demand."),
                ("Indexes", "Availability Indicators", "Published notes for delivery health, latency ranges, and regional access continuity."),
                ("Methodology", "Source Framework", "Structured explanations of how public signals, release data, and infrastructure notes are interpreted."),
            ],
            "extra": """
    <section class="section panel">
      <h2>Research Series</h2>
      <table class="content-table">
        <tr><th>Series</th><th>Cadence</th><th>Scope</th><th>Latest</th></tr>
        <tr><td>Digital Infrastructure Monitor</td><td>Monthly</td><td>Capacity, regions, operators</td><td>May 2026</td></tr>
        <tr><td>Resource Delivery Index</td><td>Weekly</td><td>Availability, mirrors, static archives</td><td>Week 22</td></tr>
        <tr><td>Enterprise Release Notes</td><td>Monthly</td><td>Versioning, manifests, package controls</td><td>May 2026</td></tr>
        <tr><td>Regional Continuity Brief</td><td>Quarterly</td><td>Americas, Europe, Asia-Pacific</td><td>Q2 2026</td></tr>
      </table>
    </section>
    <section class="section panel">
      <h2>Analyst Notes</h2>
      <div class="news-grid">
        <article><strong>Cloud delivery teams keep static artifacts in the critical path</strong><p>Public release catalogs remain valuable because they reduce dependency on account-gated dashboards during incidents.</p><span>Research note</span></article>
        <article><strong>Regional capacity planning emphasizes continuity signals</strong><p>Market teams are comparing documented availability and infrastructure expansion before allocating workloads.</p><span>Market note</span></article>
        <article><strong>Checksum manifests become part of vendor due diligence</strong><p>Procurement teams increasingly treat file integrity records as a basic operational control.</p><span>Operations note</span></article>
      </div>
    </section>
    <section class="section split">
      <div class="panel quiet">
        <h2>Research Inputs</h2>
        <p>Public filings, operator updates, network availability observations, release catalogs, procurement notes, and archived documentation updates.</p>
      </div>
      <div class="panel quiet">
        <h2>Publication Format</h2>
        <p>Research outputs are published as static pages, downloadable packets, and reusable chart sets for repeat reading and long-term reference.</p>
      </div>
    </section>""",
        },
        "markets": {
            "eyebrow": "Market coverage",
            "title": "Regional intelligence across data, delivery, and network infrastructure.",
            "intro": "Coverage pages summarize observed infrastructure conditions, resource availability, and operational indicators by business region.",
            "metric": "18",
            "metric_label": "regional markets under review",
            "cards": [
                ("Americas", "Capacity and Enterprise Demand", "Coverage of cloud regions, data center clusters, and software delivery requirements."),
                ("Europe", "Compliance-Aware Operations", "Notes on archive continuity, regional access, and documentation retention practices."),
                ("Asia-Pacific", "High-Growth Delivery Routes", "Market observations for resource distribution, latency bands, and public release access."),
            ],
            "extra": """
    <section class="section panel">
      <h2>Coverage Matrix</h2>
      <table class="content-table">
        <tr><th>Region</th><th>Primary indicators</th><th>Coverage status</th><th>Review cadence</th></tr>
        <tr><td>North America</td><td>Data center capacity, enterprise delivery, release availability</td><td>Active</td><td>Weekly</td></tr>
        <tr><td>Western Europe</td><td>Regional retention, compliance notes, documentation access</td><td>Active</td><td>Biweekly</td></tr>
        <tr><td>East Asia</td><td>Latency bands, resource mirrors, software release routes</td><td>Active</td><td>Weekly</td></tr>
        <tr><td>Southeast Asia</td><td>Connectivity growth, local access points, archive demand</td><td>Developing</td><td>Monthly</td></tr>
      </table>
    </section>
    <section class="section panel">
      <h2>Market Indicators</h2>
      <div class="profile-grid">
        <div><strong>Capacity</strong><span>Public expansion signals, regional hosting density, and data center investment notes.</span></div>
        <div><strong>Availability</strong><span>Observed access continuity, mirror behavior, and static resource delivery windows.</span></div>
        <div><strong>Release Activity</strong><span>Package cadence, documentation volume, and visible version updates.</span></div>
        <div><strong>Operational Risk</strong><span>Dependency concentration, maintenance windows, and access policy changes.</span></div>
      </div>
    </section>
    <section class="section contact-band">
      <div>
        <span class="panel-label">Regional notes</span>
        <h2>Coverage summaries are refreshed on a fixed operating calendar.</h2>
        <p>Readers can use the markets area as an at-a-glance entry point before moving into research briefs, documents, or downloadable packages.</p>
      </div>
      <div>
        <p><strong>Next update</strong><br>June 2026 regional continuity note</p>
        <p><strong>Format</strong><br>Static report, chart pack, and archive manifest</p>
      </div>
    </section>""",
        },
        "insights": {
            "eyebrow": "Insights",
            "title": "Commentary and updates from the research desk.",
            "intro": "The insights section provides shorter notes, publication updates, and operational observations between formal research releases.",
            "metric": "36",
            "metric_label": "insight notes published this year",
            "cards": [
                ("Commentary", "Infrastructure Signals", "Short market notes about infrastructure activity and delivery operations."),
                ("Updates", "Publication Activity", "Announcements for refreshed documents, archive packages, and media libraries."),
                ("Review", "Operational Lessons", "Practical observations from continuity reviews and resource publishing workflows."),
            ],
            "extra": """
    <section class="section panel">
      <h2>Latest Commentary</h2>
      <div class="news-grid">
        <article><strong>Static resource portals remain important during high-change release cycles</strong><p>Teams continue to value simple pages with predictable document paths and visible update dates.</p><span>May 28, 2026</span></article>
        <article><strong>Regional access planning moves earlier in infrastructure procurement</strong><p>Availability notes are increasingly reviewed before vendor onboarding and workload migration decisions.</p><span>May 22, 2026</span></article>
        <article><strong>Research charts are being reused across operational runbooks</strong><p>Chart packs help teams communicate capacity, release, and availability trends without rebuilding visuals.</p><span>May 14, 2026</span></article>
      </div>
    </section>
    <section class="section split">
      <div class="panel quiet">
        <h2>Editorial Calendar</h2>
        <p>Weekly resource delivery notes, monthly infrastructure summaries, quarterly market briefs, and semiannual methodology reviews.</p>
      </div>
      <div class="panel quiet">
        <h2>Subscriber Materials</h2>
        <p>Public summaries are paired with downloadable archives, chart images, and retained document snapshots for continuity and audit use.</p>
      </div>
    </section>
    <section class="section panel">
      <h2>Insight Archive</h2>
      <table class="content-table">
        <tr><th>Title</th><th>Category</th><th>Publication date</th></tr>
        <tr><td>Mirror strategies for long-lived resource pages</td><td>Operations</td><td>2026-05-09</td></tr>
        <tr><td>Digital infrastructure demand remains broad across enterprise sectors</td><td>Markets</td><td>2026-04-29</td></tr>
        <tr><td>Release manifests and checksum records support downstream trust</td><td>Documentation</td><td>2026-04-17</td></tr>
        <tr><td>Regional continuity plans become part of procurement reviews</td><td>Research</td><td>2026-03-30</td></tr>
      </table>
    </section>""",
        },
        "contact": {
            "eyebrow": "Contact",
            "title": "Resource coordination and research inquiries.",
            "intro": "Contact pages give the site a normal institutional footprint: research desk, publication requests, archive support, and regional information channels.",
            "metric": "4",
            "metric_label": "public inquiry channels",
            "cards": [
                ("Research", "Market Notes", "Questions about research series, methodology notes, and regional market summaries."),
                ("Publication", "Resource Access", "Requests related to documents, download archives, manifests, and static media packages."),
                ("Operations", "Availability Reports", "Inquiries about resource continuity notes, mirror observations, and update schedules."),
            ],
            "extra": """
    <section class="section panel">
      <h2>Contact Directory</h2>
      <table class="content-table">
        <tr><th>Desk</th><th>Use case</th><th>Email</th><th>Response window</th></tr>
        <tr><td>Research Desk</td><td>Market and methodology questions</td><td>research@globalresource.example</td><td>2 business days</td></tr>
        <tr><td>Publication Desk</td><td>Documents, archives, manifests</td><td>publications@globalresource.example</td><td>1 business day</td></tr>
        <tr><td>Media Library</td><td>Charts, diagrams, report assets</td><td>media@globalresource.example</td><td>2 business days</td></tr>
        <tr><td>Operations Review</td><td>Availability and continuity notes</td><td>operations@globalresource.example</td><td>1 business day</td></tr>
      </table>
    </section>
    <section class="section split">
      <div class="panel quiet">
        <h2>Head Office</h2>
        <p>1200 Market Street, Suite 410<br>New York, NY 10005<br>United States</p>
      </div>
      <div class="panel quiet">
        <h2>Publication Hours</h2>
        <p>Monday through Friday, 09:00-17:00 Eastern Time. Scheduled resource updates are normally published outside primary market hours.</p>
      </div>
    </section>
    <section class="section contact-band">
      <div>
        <span class="panel-label">Before contacting</span>
        <h2>Most requests can be routed by document family or archive channel.</h2>
        <p>Include the publication name, package version, region, and intended use case so the correct desk can respond with the right reference material.</p>
      </div>
      <div>
        <p><strong>Public resources</strong><br>Documents, downloads, charts, release manifests</p>
        <p><strong>Preferred format</strong><br>Email with publication identifier and request summary</p>
      </div>
    </section>""",
        },
        "docs": {
            "eyebrow": "Documentation center",
            "title": "Structured references for operational teams.",
            "intro": "Current documentation packages include integration guides, resource delivery practices, release governance, and regional availability notes.",
            "metric": "184",
            "metric_label": "maintained reference documents",
            "cards": [
                ("Library", "Resource Handbook", "Long-form operating guidance for release assets, static catalogs, and delivery practices."),
                ("Governance", "Release Controls", "Change windows, checksum policies, retention notes, and publication review trails."),
                ("Regions", "Availability Notes", "Connectivity observations and operational summaries for supported business regions."),
            ],
            "extra": """
    <section class="section panel">
      <h2>Reference Index</h2>
      <div class="search-box">Search market notes, infrastructure briefs, release controls...</div>
      <table class="content-table">
        <tr><th>Document</th><th>Category</th><th>Status</th><th>Updated</th></tr>
        <tr><td>Digital Infrastructure Overview</td><td>Research</td><td>Current</td><td>2026-05-24</td></tr>
        <tr><td>Resource Delivery Controls</td><td>Operations</td><td>Current</td><td>2026-05-20</td></tr>
        <tr><td>Mirror Availability Methodology</td><td>Reliability</td><td>Maintained</td><td>2026-05-12</td></tr>
        <tr><td>Regional Data Access Notes</td><td>Coverage</td><td>Current</td><td>2026-05-08</td></tr>
      </table>
    </section>
    <section class="section split">
      <div class="panel quiet">
        <h2>Documentation Standards</h2>
        <p>Each reference is assigned a category, publication owner, update cadence, and retention note. Substantive revisions are published as new static snapshots rather than mutable documents.</p>
      </div>
      <div class="panel quiet">
        <h2>Reader Guidance</h2>
        <p>Operational documents are written for infrastructure teams, market analysts, and publication managers who need stable references without relying on interactive systems.</p>
      </div>
    </section>
    <section class="section panel">
      <h2>Frequently Used References</h2>
      <div class="profile-grid">
        <div><strong>Release Checklist</strong><span>Pre-publication controls for manifests, checksums, archive names, and retention windows.</span></div>
        <div><strong>Regional Availability Note</strong><span>Guidance for interpreting latency, access continuity, and mirror status summaries.</span></div>
        <div><strong>Archive Naming Policy</strong><span>Recommended structure for package names, document identifiers, and static resource paths.</span></div>
        <div><strong>Publication Review Log</strong><span>A lightweight format for documenting release decisions and update approvals.</span></div>
      </div>
    </section>""",
        },
        "downloads": {
            "eyebrow": "Publication archive",
            "title": "Verified releases and research packages.",
            "intro": "Downloadable packages are grouped by publication channel, checksum status, and retention policy for predictable retrieval.",
            "metric": "428",
            "metric_label": "verified artifacts",
            "cards": [
                ("Briefs", "Research Packages", "Quarterly and monthly infrastructure briefs with static supporting materials."),
                ("Data", "Index Snapshots", "Versioned resource catalogs and structured archive bundles."),
                ("Verify", "Manifest Files", "SHA256 manifests and release notes for every public package."),
            ],
            "extra": """
    <section class="section panel">
      <h2>Release Catalog</h2>
      <table class="content-table">
        <tr><th>Package</th><th>Channel</th><th>Size</th><th>Verification</th></tr>
        <tr><td>infrastructure-brief-2026-q2.pdf</td><td>Research</td><td>18 MB</td><td>SHA256</td></tr>
        <tr><td>resource-index-2026.05.zip</td><td>Data</td><td>42 MB</td><td>SHA256</td></tr>
        <tr><td>delivery-controls-handbook.zip</td><td>Operations</td><td>24 MB</td><td>SHA256</td></tr>
        <tr><td>media-library-2026.05.tar.gz</td><td>Assets</td><td>96 MB</td><td>SHA256</td></tr>
      </table>
    </section>
    <section class="section split">
      <div class="panel quiet">
        <h2>Download Policy</h2>
        <p>Published packages are retained under stable paths. Replacement packages receive new version identifiers and updated manifest records.</p>
      </div>
      <div class="panel quiet">
        <h2>Verification Notes</h2>
        <p>Checksum records are published with every archive so downstream teams can verify file integrity before use or redistribution.</p>
      </div>
    </section>
    <section class="section panel">
      <h2>Archive Channels</h2>
      <div class="profile-grid">
        <div><strong>Research</strong><span>Market notes, infrastructure briefs, and summary packs for monthly publication cycles.</span></div>
        <div><strong>Operations</strong><span>Handbooks, checklists, and internal-facing resource continuity references.</span></div>
        <div><strong>Data</strong><span>Static indexes, structured catalogs, and versioned manifest bundles.</span></div>
        <div><strong>Media</strong><span>Charts, diagrams, and branded publication assets for reports and portals.</span></div>
      </div>
    </section>""",
        },
        "assets": {
            "eyebrow": "Media library",
            "title": "Brand, chart, and research visuals.",
            "intro": "Static visual resources support research pages, release portals, data presentations, and executive summaries.",
            "metric": "3.2K",
            "metric_label": "published visual assets",
            "cards": [
                ("Charts", "Market Graphics", "Static charts for infrastructure, data center, and resource delivery reports."),
                ("Systems", "Architecture Diagrams", "Versioned diagrams for operational and documentation packages."),
                ("Brand", "Publication Assets", "Presentation images, icons, and executive summary media."),
            ],
            "extra": f"""
    <section class="section panel">
      <h2>Asset Collections</h2>
      <div class="asset-grid">
        <div><span class="thumb a">{chart_svg}</span><strong>Research Charts</strong><p>Regional infrastructure and availability charts.</p></div>
        <div><span class="thumb b">{network_svg}</span><strong>Network Diagrams</strong><p>Static diagrams for resource and delivery documentation.</p></div>
        <div><span class="thumb c">{media_svg}</span><strong>Publication Media</strong><p>Images and icons for reports, portals, and release notes.</p></div>
      </div>
    </section>
    <section class="section panel">
      <h2>Media Usage Notes</h2>
      <p>Visual assets are grouped by report family and publication period. Each package includes optimized web images, fallback formats, and simple usage notes for internal documentation and public portals.</p>
      <div class="profile-grid">
        <div><strong>Chart Sets</strong><span>Prepared graphics for infrastructure briefs and data availability summaries.</span></div>
        <div><strong>Diagram Packs</strong><span>Operational diagrams for delivery architecture, resource flow, and publication lifecycle notes.</span></div>
        <div><strong>Presentation Media</strong><span>Executive summary graphics and static images for recurring business reviews.</span></div>
        <div><strong>Icon Library</strong><span>Small interface and document icons for release catalogs and web references.</span></div>
      </div>
    </section>""",
        },
    }
    page = pages.get(section, pages["home"])
    card_links = {
        "home": [nav_research, nav_downloads, nav_markets],
        "about": [nav_markets, nav_docs, nav_contact],
        "research": [nav_downloads, nav_markets, nav_docs],
        "markets": [nav_research, nav_docs, nav_insights],
        "insights": [nav_research, nav_downloads, nav_docs],
        "docs": [nav_downloads, nav_insights, nav_markets],
        "downloads": [nav_research, nav_docs, nav_assets],
        "assets": [nav_research, nav_docs, nav_downloads],
        "contact": [nav_research, nav_downloads, nav_markets],
    }.get(section, [nav_home, nav_docs, nav_downloads])
    cards = "\n".join(
        f'      <a class="panel feature" href="{card_links[index]}"><span class="kicker">{label}</span><strong>{title}</strong><p>{desc}</p><span class="card-action">Read more</span></a>'
        for index, (label, title, desc) in enumerate(page["cards"])
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
      --ink: #13202d;
      --muted: #617081;
      --line: #d8e0e9;
      --panel: #ffffff;
      --wash: #f2f5f8;
      --deep: #0f2436;
      --accent: #1c6b72;
      --accent-2: #b48a3c;
      --ok: #157347;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background: var(--wash);
      line-height: 1.55;
    }}
    a {{ color: inherit; }}
    header {{
      background: rgba(255,255,255,.96);
      border-bottom: 1px solid var(--line);
      position: sticky;
      top: 0;
      z-index: 5;
      backdrop-filter: blur(8px);
    }}
    .wrap {{ width: min(1120px, calc(100% - 32px)); margin: 0 auto; }}
    .nav {{ display: flex; align-items: center; justify-content: space-between; min-height: 64px; gap: 20px; }}
    .brand {{ font-weight: 700; font-size: 18px; display: flex; gap: 10px; align-items: center; letter-spacing: .03em; }}
    .brand-mark {{ width: 30px; height: 30px; border-radius: 50%; background: radial-gradient(circle at 35% 35%, #fff, var(--accent-2) 18%, var(--deep) 70%); display: inline-block; }}
    nav {{ display: flex; align-items: center; justify-content: flex-end; gap: 18px; flex-wrap: wrap; }}
    nav a {{ color: var(--muted); text-decoration: none; font-size: 13px; padding: 8px 0; border-bottom: 2px solid transparent; text-transform: uppercase; letter-spacing: .08em; }}
    nav a.active {{ color: var(--ink); border-bottom-color: var(--accent); }}
    main {{ padding: 0 0 48px; }}
    .hero-band {{ background: var(--deep); color: #fff; padding: 70px 0 34px; }}
    .hero {{ display: grid; grid-template-columns: 1.18fr .82fr; gap: 36px; align-items: stretch; }}
    h1 {{ font-size: clamp(38px, 5vw, 68px); line-height: .98; margin: 0 0 18px; letter-spacing: 0; font-weight: 500; }}
    h2 {{ margin: 0 0 14px; font-size: 26px; font-weight: 500; }}
    p {{ margin: 0 0 16px; color: var(--muted); }}
    .hero p, .hero .lede {{ color: #d5dee7; }}
    .lede {{ font-size: 19px; color: #344457; }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 2px;
      padding: 24px;
      box-shadow: 0 18px 50px rgba(15, 36, 54, .08);
    }}
    .hero-card {{ background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.18); box-shadow: none; }}
    .hero-card p {{ color: #d5dee7; }}
    .top-strip {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 0; border: 1px solid var(--line); background: #fff; margin: -1px auto 34px; }}
    .top-strip div {{ border-right: 1px solid var(--line); padding: 18px; }}
    .top-strip div:last-child {{ border-right: 0; }}
    .top-strip strong {{ display: block; font-size: 24px; color: var(--deep); }}
    .top-strip span {{ color: var(--muted); font-size: 13px; text-transform: uppercase; letter-spacing: .06em; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; margin-top: 24px; }}
    .metric {{ font-size: 36px; font-weight: 500; color: var(--accent-2); }}
    .panel-label, .kicker {{ color: var(--accent-2); font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .12em; }}
    .feature strong {{ display: block; margin: 8px 0; font-size: 20px; font-weight: 500; }}
    a.feature {{ display: block; text-decoration: none; transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease; }}
    a.feature:hover, a.feature:focus-visible {{ transform: translateY(-2px); border-color: var(--accent); box-shadow: 0 22px 54px rgba(15, 36, 54, .12); outline: none; }}
    .card-action {{ display: inline-flex; align-items: center; margin-top: 4px; color: var(--accent); font: 700 13px Arial, Helvetica, sans-serif; text-transform: uppercase; letter-spacing: .06em; }}
    .card-action::after {{ content: ""; width: 7px; height: 7px; margin-left: 8px; border-top: 2px solid currentColor; border-right: 2px solid currentColor; transform: rotate(45deg); }}
    .list {{ margin: 0; padding-left: 20px; color: var(--muted); }}
    .list.compact li {{ margin-bottom: 6px; }}
    .section {{ margin-top: 34px; }}
    .split {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
    .editorial {{ display: grid; grid-template-columns: .9fr 1.1fr; gap: 34px; background: #fff; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); padding: 36px 0; }}
    .insight-list {{ display: grid; gap: 12px; }}
    .insight-list article {{ border-left: 3px solid var(--accent-2); background: #f8fafc; padding: 14px 16px; }}
    .insight-list strong {{ display: block; margin-bottom: 4px; font-weight: 500; }}
    .insight-list span {{ color: var(--muted); }}
    .profile-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-top: 18px; }}
    .profile-grid div {{ border: 1px solid var(--line); background: #f8fafc; padding: 16px; }}
    .profile-grid strong {{ display: block; margin-bottom: 8px; font-weight: 500; }}
    .profile-grid span {{ color: var(--muted); }}
    .news-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; margin-top: 18px; }}
    .news-grid article {{ border-top: 3px solid var(--accent-2); background: #f8fafc; padding: 18px; }}
    .news-grid strong {{ display: block; font-size: 18px; font-weight: 500; margin-bottom: 10px; }}
    .news-grid span {{ color: var(--accent); font-size: 13px; text-transform: uppercase; letter-spacing: .08em; }}
    .contact-band {{ display: grid; grid-template-columns: 1.2fr .8fr; gap: 24px; background: var(--deep); color: #fff; padding: 34px; }}
    .contact-band p {{ color: #d5dee7; }}
    .hero-actions {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 22px; }}
    .primary-link, .secondary-link {{ min-height: 44px; display: inline-flex; align-items: center; padding: 10px 16px; border-radius: 2px; text-decoration: none; font-weight: 700; font-family: Arial, Helvetica, sans-serif; }}
    .primary-link {{ background: var(--accent-2); color: #13202d; }}
    .secondary-link {{ border: 1px solid rgba(255,255,255,.42); color: #fff; background: transparent; }}
    .mini-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 14px; }}
    .mini-grid span {{ border: 1px solid rgba(255,255,255,.18); padding: 10px; color: #d5dee7; background: rgba(255,255,255,.06); }}
    .mini-grid strong {{ color: #fff; float: right; }}
    .release-row {{ display: grid; grid-template-columns: 1fr auto auto; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--line); }}
    .release-row:last-child {{ border-bottom: 0; }}
    .release-row em {{ color: var(--accent-2); font-style: normal; }}
    .search-box {{ border: 1px solid var(--line); background: #fff; border-radius: 2px; padding: 13px 14px; color: var(--muted); margin-bottom: 14px; }}
    .content-table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
    .content-table th, .content-table td {{ text-align: left; border-bottom: 1px solid var(--line); padding: 12px 10px; }}
    .content-table th {{ color: var(--muted); font-size: 13px; }}
    .asset-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }}
    .asset-grid div {{ border: 1px solid var(--line); border-radius: 2px; padding: 14px; }}
    .thumb {{ display: block; min-height: 110px; margin-bottom: 12px; border-radius: 2px; background: #f6f8fb; border: 1px solid var(--line); overflow: hidden; }}
    .thumb svg {{ display: block; width: 100%; height: 100%; min-height: 110px; }}
    .thumb.b {{ background: linear-gradient(135deg, #e2e7ed, #cfd8df); }}
    .thumb.c {{ background: linear-gradient(135deg, #efe7d8, #d9e4e4); }}
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
      .hero, .grid, .split, .top-strip, .asset-grid, .editorial, .profile-grid, .news-grid, .contact-band {{ grid-template-columns: 1fr; }}
      .hero-band {{ padding: 42px 0 26px; }}
      .nav {{ align-items: flex-start; flex-direction: column; padding: 14px 0; }}
      nav {{ justify-content: flex-start; gap: 14px; }}
      .top-strip div {{ border-right: 0; border-bottom: 1px solid var(--line); }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="wrap nav">
      <div class="brand"><span class="brand-mark"></span>{site_name}</div>
      <nav>
        <a class="{active["home"]}" href="{nav_home}">Home</a>
        <a class="{active["about"]}" href="{nav_about}">About</a>
        <a class="{active["research"]}" href="{nav_research}">Research</a>
        <a class="{active["markets"]}" href="{nav_markets}">Markets</a>
        <a class="{active["insights"]}" href="{nav_insights}">Insights</a>
        <a class="{active["docs"]}" href="{nav_docs}">Docs</a>
        <a class="{active["downloads"]}" href="{nav_downloads}">Downloads</a>
        <a class="{active["assets"]}" href="{nav_assets}">Assets</a>
        <a class="{active["contact"]}" href="{nav_contact}">Contact</a>
      </nav>
    </div>
  </header>
  <section class="hero-band">
    <div class="wrap hero">
        <div>
          <span class="panel-label">{page["eyebrow"]}</span>
          <h1>{page["title"]}</h1>
          <p class="lede">{page["intro"]}</p>
          <div class="hero-actions">
            <a class="primary-link" href="{nav_downloads}">View publications</a>
            <a class="secondary-link" href="{nav_docs}">Research library</a>
          </div>
        </div>
        <div class="panel hero-card">
          <div class="panel-label">Firm indicator</div>
          <div class="metric">{page["metric"]}</div>
          <p>{page["metric_label"]}</p>
          <div class="mini-grid">
            <span>Americas <strong>active</strong></span>
            <span>Europe <strong>active</strong></span>
            <span>Asia-Pacific <strong>active</strong></span>
            <span>Research <strong>current</strong></span>
          </div>
        </div>
    </div>
  </section>
  <main class="wrap">
    <section class="top-strip">
      <div><strong>18</strong><span>covered regions</span></div>
      <div><strong>428</strong><span>published artifacts</span></div>
      <div><strong>24h</strong><span>operations review</span></div>
      <div><strong>TLS</strong><span>secure delivery</span></div>
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
        about_html=render_site_html(site, "about"),
        research_html=render_site_html(site, "research"),
        markets_html=render_site_html(site, "markets"),
        insights_html=render_site_html(site, "insights"),
        contact_html=render_site_html(site, "contact"),
    )
