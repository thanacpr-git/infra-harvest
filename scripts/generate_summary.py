#!/usr/bin/env python3
"""
generate_summary.py — Generate an HTML inventory summary report.
Usage: python3 generate_summary.py <PROJECT_DIR>

Produces a detailed HTML report with:
- Executive overview with resource counts
- Sortable/filterable resource table
- Network topology section
- Connection matrix
- Copy-to-clipboard ARNs
- CSV export
"""

import json
import sys
from pathlib import Path
from datetime import datetime


def generate_summary(project_dir: str):
    """Generate the inventory summary HTML."""
    enriched_path = Path(project_dir) / "enriched.json"
    connections_path = Path(project_dir) / "connections.json"

    if not enriched_path.exists():
        print(f"ERROR: {enriched_path} not found.")
        sys.exit(1)

    with open(enriched_path) as f:
        enriched_data = json.load(f)

    conn_data = None
    if connections_path.exists():
        with open(connections_path) as f:
            conn_data = json.load(f)

    resources = enriched_data["resources"]
    metadata = enriched_data["metadata"]

    # Compute stats
    service_counts = {}
    type_counts = {}
    for r in resources:
        svc = r["service"]
        rtype = r["resource_type"]
        service_counts[svc] = service_counts.get(svc, 0) + 1
        type_counts[f"{svc}/{rtype}"] = type_counts.get(f"{svc}/{rtype}", 0) + 1

    # Sort by count
    service_counts_sorted = sorted(service_counts.items(), key=lambda x: -x[1])

    # Build resource rows for table
    table_rows = []
    for r in resources:
        details = r.get("details") or {}
        # Build key config string
        config_parts = []
        if r["service"] == "ec2" and r["resource_type"] == "instance":
            config_parts.append(f"Type: {details.get('instance_type', 'N/A')}")
            config_parts.append(f"State: {details.get('state', 'N/A')}")
        elif r["service"] == "rds":
            config_parts.append(f"Engine: {details.get('engine', 'N/A')} {details.get('engine_version', '')}")
            config_parts.append(f"Class: {details.get('instance_class', 'N/A')}")
            config_parts.append(f"Multi-AZ: {details.get('multi_az', 'N/A')}")
        elif r["service"] == "lambda":
            config_parts.append(f"Runtime: {details.get('runtime', 'N/A')}")
            config_parts.append(f"Memory: {details.get('memory_mb', 'N/A')}MB")
        elif r["service"] == "elasticloadbalancing":
            config_parts.append(f"Type: {details.get('type', 'N/A')}")
            config_parts.append(f"Scheme: {details.get('scheme', 'N/A')}")
        elif r["resource_type"] == "vpc":
            config_parts.append(f"CIDR: {details.get('cidr_block', 'N/A')}")
        elif r["resource_type"] == "subnet":
            config_parts.append(f"CIDR: {details.get('cidr_block', 'N/A')}")
            config_parts.append(f"AZ: {details.get('availability_zone', 'N/A')}")

        tags = r.get("tags", {})
        name = tags.get("Name", tags.get("name", r["resource_id"]))

        table_rows.append({
            "service": r["service"],
            "type": r["resource_type"],
            "name": name,
            "id": r["resource_id"],
            "arn": r["arn"],
            "region": r["region"],
            "az": details.get("availability_zone", ""),
            "vpc_id": details.get("vpc_id", ""),
            "config": " | ".join(config_parts),
            "tags": ", ".join(f"{k}={v}" for k, v in tags.items() if k != "Name"),
        })

    # Connection stats
    conn_stats = {}
    if conn_data:
        conn_stats = conn_data.get("stats", {}).get("connection_types", {})

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Infrastructure Inventory Summary</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Amazon Ember', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f8f9fa;
            color: #232F3E;
            line-height: 1.6;
        }}
        .header {{
            background: #232F3E;
            color: white;
            padding: 25px 30px;
        }}
        .header h1 {{
            font-size: 1.6rem;
            font-weight: 500;
            margin-bottom: 5px;
        }}
        .header .subtitle {{
            font-size: 0.85rem;
            opacity: 0.8;
        }}
        .content {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 30px;
        }}
        .overview-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: white;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
        }}
        .stat-card .value {{
            font-size: 2rem;
            font-weight: 700;
            color: #FF9900;
        }}
        .stat-card .label {{
            font-size: 0.8rem;
            color: #666;
            margin-top: 5px;
        }}
        .section {{
            background: white;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            margin-bottom: 20px;
            overflow: hidden;
        }}
        .section-header {{
            background: #f8f9fa;
            padding: 15px 20px;
            border-bottom: 1px solid #e0e0e0;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .section-header h2 {{
            font-size: 1rem;
            font-weight: 600;
        }}
        .section-header .toggle {{
            font-size: 1.2rem;
            color: #666;
        }}
        .section-body {{
            padding: 20px;
        }}
        .section-body.collapsed {{
            display: none;
        }}
        .filter-bar {{
            margin-bottom: 15px;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .filter-bar input {{
            padding: 8px 14px;
            border: 1px solid #ccc;
            border-radius: 4px;
            font-size: 0.85rem;
            width: 300px;
        }}
        .filter-bar select {{
            padding: 8px 14px;
            border: 1px solid #ccc;
            border-radius: 4px;
            font-size: 0.85rem;
        }}
        .filter-bar button {{
            padding: 8px 14px;
            background: #FF9900;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.85rem;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.8rem;
        }}
        th {{
            background: #f8f9fa;
            padding: 10px 12px;
            text-align: left;
            border-bottom: 2px solid #e0e0e0;
            font-weight: 600;
            cursor: pointer;
            white-space: nowrap;
        }}
        th:hover {{
            background: #e8e8e8;
        }}
        td {{
            padding: 8px 12px;
            border-bottom: 1px solid #f0f0f0;
            vertical-align: top;
        }}
        tr:hover {{
            background: #fafafa;
        }}
        .arn-cell {{
            font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
            font-size: 0.7rem;
            color: #666;
            cursor: pointer;
            max-width: 300px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .arn-cell:hover {{
            color: #FF9900;
            text-decoration: underline;
        }}
        .service-badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 0.7rem;
            font-weight: 500;
            color: white;
        }}
        .service-badge.ec2 {{ background: #ED7100; }}
        .service-badge.rds {{ background: #3B48CC; }}
        .service-badge.lambda {{ background: #ED7100; }}
        .service-badge.elasticloadbalancing {{ background: #8C4FFF; }}
        .service-badge.s3 {{ background: #3F8624; }}
        .service-badge.dynamodb {{ background: #3B48CC; }}
        .service-badge.default {{ background: #545b64; }}
        .breakdown-chart {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 10px;
        }}
        .breakdown-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 12px;
            background: #f8f9fa;
            border-radius: 4px;
            font-size: 0.8rem;
        }}
        .breakdown-item .count {{
            font-weight: 700;
            color: #FF9900;
        }}
        .copy-toast {{
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: #232F3E;
            color: white;
            padding: 10px 20px;
            border-radius: 6px;
            font-size: 0.85rem;
            opacity: 0;
            transition: opacity 0.3s;
            pointer-events: none;
        }}
        .copy-toast.show {{
            opacity: 1;
        }}
        @media print {{
            .filter-bar, .toggle {{ display: none !important; }}
            .section-body.collapsed {{ display: block !important; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Infrastructure Inventory Summary</h1>
        <div class="subtitle">
            Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} |
            Method: {metadata.get('discovery_method', 'unknown')} |
            Account: {metadata.get('account_id', 'N/A')} |
            Region: {', '.join(metadata.get('regions', []))}
        </div>
    </div>

    <div class="content">
        <!-- Overview Cards -->
        <div class="overview-grid">
            <div class="stat-card">
                <div class="value">{len(resources)}</div>
                <div class="label">Total Resources</div>
            </div>
            <div class="stat-card">
                <div class="value">{len(service_counts)}</div>
                <div class="label">AWS Services</div>
            </div>
            <div class="stat-card">
                <div class="value">{len(metadata.get('vpc_ids', []))}</div>
                <div class="label">VPCs</div>
            </div>
            <div class="stat-card">
                <div class="value">{metadata.get('enriched_count', 0)}</div>
                <div class="label">Enriched</div>
            </div>
            <div class="stat-card">
                <div class="value">{sum(conn_stats.values()) if conn_stats else 0}</div>
                <div class="label">Connections</div>
            </div>
        </div>

        <!-- Service Breakdown -->
        <div class="section">
            <div class="section-header" onclick="toggleSection(this)">
                <h2>📦 Service Breakdown</h2>
                <span class="toggle">▼</span>
            </div>
            <div class="section-body">
                <div class="breakdown-chart">
"""

    for svc, count in service_counts_sorted:
        html += f'                    <div class="breakdown-item"><span class="count">{count}</span> {svc}</div>\n'

    html += """                </div>
            </div>
        </div>

        <!-- Resource Table -->
        <div class="section">
            <div class="section-header" onclick="toggleSection(this)">
                <h2>📋 Resource Inventory</h2>
                <span class="toggle">▼</span>
            </div>
            <div class="section-body">
                <div class="filter-bar">
                    <input type="text" id="searchInput" placeholder="Search by name, ARN, or config..." onkeyup="filterTable()">
                    <select id="serviceFilter" onchange="filterTable()">
                        <option value="">All Services</option>
"""

    for svc, _ in service_counts_sorted:
        html += f'                        <option value="{svc}">{svc} ({service_counts[svc]})</option>\n'

    html += """                    </select>
                    <button onclick="exportCSV()">📥 Export CSV</button>
                </div>
                <div style="overflow-x: auto;">
                <table id="resourceTable">
                    <thead>
                        <tr>
                            <th onclick="sortTable(0)">Service ↕</th>
                            <th onclick="sortTable(1)">Type ↕</th>
                            <th onclick="sortTable(2)">Name ↕</th>
                            <th onclick="sortTable(3)">ARN</th>
                            <th onclick="sortTable(4)">Region ↕</th>
                            <th onclick="sortTable(5)">VPC ↕</th>
                            <th onclick="sortTable(6)">Config</th>
                            <th onclick="sortTable(7)">Tags</th>
                        </tr>
                    </thead>
                    <tbody>
"""

    for row in table_rows:
        badge_class = row["service"] if row["service"] in ("ec2", "rds", "lambda", "elasticloadbalancing", "s3", "dynamodb") else "default"
        html += f"""                        <tr data-service="{row['service']}">
                            <td><span class="service-badge {badge_class}">{row['service']}</span></td>
                            <td>{row['type']}</td>
                            <td><strong>{row['name']}</strong></td>
                            <td class="arn-cell" onclick="copyArn(this)" title="Click to copy">{row['arn']}</td>
                            <td>{row['region']}</td>
                            <td>{row['vpc_id']}</td>
                            <td>{row['config']}</td>
                            <td style="font-size: 0.7rem; color: #666;">{row['tags'][:80]}</td>
                        </tr>
"""

    html += """                    </tbody>
                </table>
                </div>
            </div>
        </div>
"""

    # Connection Types section
    if conn_stats:
        html += """        <!-- Connections -->
        <div class="section">
            <div class="section-header" onclick="toggleSection(this)">
                <h2>🔗 Connection Types</h2>
                <span class="toggle">▼</span>
            </div>
            <div class="section-body">
                <div class="breakdown-chart">
"""
        for ctype, count in sorted(conn_stats.items(), key=lambda x: -x[1]):
            html += f'                    <div class="breakdown-item"><span class="count">{count}</span> {ctype}</div>\n'
        html += """                </div>
            </div>
        </div>
"""

    html += """
    </div>

    <div class="copy-toast" id="copyToast">✅ ARN copied to clipboard</div>

    <script>
        function toggleSection(header) {
            const body = header.nextElementSibling;
            const toggle = header.querySelector('.toggle');
            body.classList.toggle('collapsed');
            toggle.textContent = body.classList.contains('collapsed') ? '▶' : '▼';
        }

        function filterTable() {
            const search = document.getElementById('searchInput').value.toLowerCase();
            const service = document.getElementById('serviceFilter').value;
            const rows = document.querySelectorAll('#resourceTable tbody tr');

            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                const rowService = row.dataset.service;
                const matchSearch = !search || text.includes(search);
                const matchService = !service || rowService === service;
                row.style.display = (matchSearch && matchService) ? '' : 'none';
            });
        }

        function sortTable(colIndex) {
            const table = document.getElementById('resourceTable');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));

            rows.sort((a, b) => {
                const aText = a.cells[colIndex].textContent.trim();
                const bText = b.cells[colIndex].textContent.trim();
                return aText.localeCompare(bText);
            });

            rows.forEach(row => tbody.appendChild(row));
        }

        function copyArn(cell) {
            navigator.clipboard.writeText(cell.textContent).then(() => {
                const toast = document.getElementById('copyToast');
                toast.classList.add('show');
                setTimeout(() => toast.classList.remove('show'), 2000);
            });
        }

        function exportCSV() {
            const table = document.getElementById('resourceTable');
            const rows = table.querySelectorAll('tr');
            let csv = '';

            rows.forEach(row => {
                if (row.style.display === 'none') return;
                const cells = row.querySelectorAll('th, td');
                const rowData = Array.from(cells).map(cell =>
                    '"' + cell.textContent.replace(/"/g, '""').trim() + '"'
                );
                csv += rowData.join(',') + '\\n';
            });

            const blob = new Blob([csv], {type: 'text/csv'});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'infrastructure-inventory.csv';
            a.click();
            URL.revokeObjectURL(url);
        }
    </script>
</body>
</html>"""

    output_path = Path(project_dir) / "inventory-summary.html"
    with open(output_path, "w") as f:
        f.write(html)

    print(f"=== Summary Generated ===")
    print(f"  Output: {output_path}")
    print(f"  Resources: {len(resources)}")
    print(f"  Services: {len(service_counts)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 generate_summary.py <PROJECT_DIR>")
        sys.exit(1)
    generate_summary(sys.argv[1])
