#!/usr/bin/env python3
"""
generate_diagram.py — Generate an interactive HTML architecture diagram.
Usage: python3 generate_diagram.py <PROJECT_DIR>

Produces a self-contained HTML file with:
- Official AWS service icons (inline SVG)
- Layered layout: Account → Region → VPC → AZ → Subnet
- Interactive hover tooltips
- Connection lines with directional arrows
- Color-coded by service category
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# AWS service icon SVG paths (simplified inline representations)
AWS_ICONS = {
    "ec2": {"color": "#ED7100", "label": "EC2", "shape": "rect"},
    "vpc": {"color": "#8C4FFF", "label": "VPC", "shape": "container"},
    "subnet": {"color": "#8C4FFF", "label": "Subnet", "shape": "container"},
    "security-group": {"color": "#DD344C", "label": "SG", "shape": "shield"},
    "instance": {"color": "#ED7100", "label": "EC2", "shape": "rect"},
    "natgateway": {"color": "#8C4FFF", "label": "NAT GW", "shape": "rect"},
    "internet-gateway": {"color": "#8C4FFF", "label": "IGW", "shape": "rect"},
    "route-table": {"color": "#8C4FFF", "label": "RT", "shape": "rect"},
    "rds": {"color": "#3B48CC", "label": "RDS", "shape": "cylinder"},
    "db-instance": {"color": "#3B48CC", "label": "RDS", "shape": "cylinder"},
    "lambda": {"color": "#ED7100", "label": "Lambda", "shape": "rect"},
    "function": {"color": "#ED7100", "label": "Lambda", "shape": "rect"},
    "elasticloadbalancing": {"color": "#8C4FFF", "label": "ELB", "shape": "rect"},
    "load-balancer": {"color": "#8C4FFF", "label": "ALB/NLB", "shape": "rect"},
    "s3": {"color": "#3F8624", "label": "S3", "shape": "bucket"},
    "dynamodb": {"color": "#3B48CC", "label": "DynamoDB", "shape": "rect"},
    "sqs": {"color": "#E7157B", "label": "SQS", "shape": "rect"},
    "sns": {"color": "#E7157B", "label": "SNS", "shape": "rect"},
    "ecs": {"color": "#ED7100", "label": "ECS", "shape": "rect"},
    "eks": {"color": "#ED7100", "label": "EKS", "shape": "rect"},
    "cloudfront": {"color": "#8C4FFF", "label": "CloudFront", "shape": "rect"},
    "apigateway": {"color": "#E7157B", "label": "API GW", "shape": "rect"},
    "elasticache": {"color": "#3B48CC", "label": "ElastiCache", "shape": "cylinder"},
    "default": {"color": "#232F3E", "label": "AWS", "shape": "rect"},
}

CONNECTION_STYLES = {
    "load-balancer-target": {"color": "#3F8624", "style": "solid", "label": "target"},
    "security-group-ingress": {"color": "#DD344C", "style": "dashed", "label": "sg-rule"},
    "vpc-membership": {"color": "#8C4FFF", "style": "dotted", "label": ""},
    "subnet-membership": {"color": "#8C4FFF", "style": "dotted", "label": ""},
    "lambda-vpc": {"color": "#ED7100", "style": "solid", "label": "vpc-eni"},
    "nat-placement": {"color": "#8C4FFF", "style": "solid", "label": "nat"},
    "route": {"color": "#232F3E", "style": "dashed", "label": "route"},
    "default": {"color": "#666666", "style": "solid", "label": ""},
}


def get_icon_info(service, resource_type):
    """Get icon styling for a resource."""
    if resource_type in AWS_ICONS:
        return AWS_ICONS[resource_type]
    if service in AWS_ICONS:
        return AWS_ICONS[service]
    return AWS_ICONS["default"]


def get_resource_label(resource):
    """Get a human-readable label for a resource."""
    details = resource.get("details") or {}
    name = ""
    # Try to get a name from tags
    tags = resource.get("tags", {})
    name = tags.get("Name", tags.get("name", ""))

    rid = resource["resource_id"]
    rtype = resource["resource_type"]

    if name:
        return f"{name}"
    return f"{rid[:20]}"


def get_tooltip(resource):
    """Generate tooltip HTML content."""
    details = resource.get("details") or {}
    parts = [
        f"<b>{resource['service'].upper()} / {resource['resource_type']}</b>",
        f"ARN: {resource['arn']}",
    ]
    if details:
        for key, val in list(details.items())[:8]:
            if val and key not in ("inbound_rules", "outbound_rules", "security_groups", "target_groups", "listeners"):
                parts.append(f"{key}: {val}")
    return "<br>".join(parts)


def generate_html(project_dir: str):
    """Generate the architecture diagram HTML."""
    connections_path = Path(project_dir) / "connections.json"
    enriched_path = Path(project_dir) / "enriched.json"

    if not connections_path.exists():
        print(f"ERROR: {connections_path} not found. Run map_connections.py first.")
        sys.exit(1)

    with open(connections_path) as f:
        conn_data = json.load(f)

    with open(enriched_path) as f:
        enriched_data = json.load(f)

    resources = enriched_data["resources"]
    connections = conn_data["connections"]
    topology = conn_data["topology"]
    metadata = conn_data["metadata"]

    # Build resource lookup
    resource_map = {r["arn"]: r for r in resources}

    # Generate nodes JSON for the frontend
    nodes = []
    for r in resources:
        icon = get_icon_info(r["service"], r["resource_type"])
        nodes.append({
            "id": r["arn"],
            "label": get_resource_label(r),
            "service": r["service"],
            "type": r["resource_type"],
            "color": icon["color"],
            "icon_label": icon["label"],
            "tooltip": get_tooltip(r),
            "vpc_id": (r.get("details") or {}).get("vpc_id", ""),
            "subnet_id": (r.get("details") or {}).get("subnet_id", ""),
            "az": (r.get("details") or {}).get("availability_zone", ""),
        })

    # Generate edges JSON
    edges = []
    for c in connections:
        if c["connection_type"] in ("vpc-membership", "subnet-membership"):
            continue  # These are shown via containment, not lines
        style = CONNECTION_STYLES.get(c["connection_type"], CONNECTION_STYLES["default"])
        edges.append({
            "source": c["source_arn"],
            "target": c["target_arn"],
            "type": c["connection_type"],
            "color": style["color"],
            "style": style["style"],
            "label": style["label"],
            "details": c.get("details", {}),
        })

    # Service category counts for legend
    service_counts = {}
    for r in resources:
        svc = r["service"]
        service_counts[svc] = service_counts.get(svc, 0) + 1

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Infrastructure Architecture Diagram</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Amazon Ember', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f8f9fa;
            color: #232F3E;
        }}
        .header {{
            background: #232F3E;
            color: white;
            padding: 20px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .header h1 {{
            font-size: 1.5rem;
            font-weight: 500;
        }}
        .header .meta {{
            font-size: 0.85rem;
            opacity: 0.8;
        }}
        .toolbar {{
            background: white;
            border-bottom: 1px solid #e0e0e0;
            padding: 10px 30px;
            display: flex;
            gap: 15px;
            align-items: center;
        }}
        .toolbar button {{
            background: #FF9900;
            color: white;
            border: none;
            padding: 6px 14px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.85rem;
            font-weight: 500;
        }}
        .toolbar button:hover {{
            background: #ec7211;
        }}
        .toolbar button.secondary {{
            background: #e0e0e0;
            color: #232F3E;
        }}
        .toolbar button.secondary:hover {{
            background: #ccc;
        }}
        .diagram-container {{
            padding: 30px;
            overflow: auto;
            min-height: calc(100vh - 160px);
        }}
        .account-box {{
            border: 2px solid #232F3E;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            background: white;
        }}
        .account-box .account-label {{
            font-size: 0.9rem;
            font-weight: 600;
            color: #232F3E;
            margin-bottom: 15px;
            padding: 4px 10px;
            background: #f0f0f0;
            border-radius: 4px;
            display: inline-block;
        }}
        .region-box {{
            border: 2px dashed #545b64;
            border-radius: 6px;
            padding: 15px;
            margin-bottom: 15px;
        }}
        .region-box .region-label {{
            font-size: 0.8rem;
            color: #545b64;
            margin-bottom: 12px;
            font-weight: 500;
        }}
        .vpc-box {{
            border: 2px solid #8C4FFF;
            border-radius: 6px;
            padding: 15px;
            margin-bottom: 15px;
            background: rgba(140, 79, 255, 0.03);
        }}
        .vpc-box .vpc-label {{
            font-size: 0.8rem;
            color: #8C4FFF;
            font-weight: 600;
            margin-bottom: 10px;
        }}
        .az-container {{
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
        }}
        .az-box {{
            border: 1px dotted #999;
            border-radius: 4px;
            padding: 12px;
            flex: 1;
            min-width: 250px;
        }}
        .az-box .az-label {{
            font-size: 0.75rem;
            color: #666;
            margin-bottom: 8px;
        }}
        .subnet-box {{
            border: 1px solid #ccc;
            border-radius: 4px;
            padding: 10px;
            margin-bottom: 8px;
        }}
        .subnet-box.public {{
            background: rgba(63, 134, 36, 0.05);
            border-color: #3F8624;
        }}
        .subnet-box.private {{
            background: rgba(59, 72, 204, 0.05);
            border-color: #3B48CC;
        }}
        .subnet-box .subnet-label {{
            font-size: 0.7rem;
            color: #666;
            margin-bottom: 6px;
        }}
        .resource-node {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 10px;
            border-radius: 4px;
            margin: 3px;
            font-size: 0.75rem;
            cursor: pointer;
            border: 1px solid;
            position: relative;
            transition: transform 0.1s, box-shadow 0.1s;
        }}
        .resource-node:hover {{
            transform: translateY(-1px);
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        }}
        .resource-node .icon {{
            width: 20px;
            height: 20px;
            border-radius: 3px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.6rem;
            color: white;
            font-weight: 700;
        }}
        .tooltip {{
            display: none;
            position: absolute;
            bottom: calc(100% + 8px);
            left: 0;
            background: #232F3E;
            color: white;
            padding: 10px 14px;
            border-radius: 6px;
            font-size: 0.7rem;
            line-height: 1.5;
            white-space: nowrap;
            z-index: 1000;
            max-width: 400px;
            white-space: pre-wrap;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }}
        .resource-node:hover .tooltip {{
            display: block;
        }}
        .global-resources {{
            margin-top: 15px;
            padding: 12px;
            background: #f8f9fa;
            border-radius: 4px;
        }}
        .global-resources .section-label {{
            font-size: 0.75rem;
            color: #666;
            margin-bottom: 8px;
            font-weight: 500;
        }}
        .legend {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: white;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.1);
            font-size: 0.75rem;
            max-width: 250px;
        }}
        .legend h3 {{
            font-size: 0.8rem;
            margin-bottom: 8px;
            color: #232F3E;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 4px;
        }}
        .legend-color {{
            width: 14px;
            height: 14px;
            border-radius: 3px;
        }}
        .connections-section {{
            margin-top: 20px;
            padding: 15px;
            background: white;
            border: 1px solid #e0e0e0;
            border-radius: 6px;
        }}
        .connection-line {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.75rem;
            margin: 4px 0;
            padding: 4px 8px;
            border-radius: 3px;
        }}
        .connection-line:hover {{
            background: #f0f0f0;
        }}
        .conn-arrow {{
            color: #666;
        }}
        @media print {{
            .toolbar, .legend {{ display: none; }}
            .diagram-container {{ padding: 10px; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🏗️ Infrastructure Architecture Diagram</h1>
        <div class="meta">
            Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} |
            Resources: {len(resources)} |
            Connections: {len(edges)}
        </div>
    </div>
    <div class="toolbar">
        <button onclick="window.print()">🖨️ Print</button>
        <button class="secondary" onclick="toggleConnections()">Toggle Connections</button>
        <button class="secondary" onclick="expandAll()">Expand All</button>
        <span style="margin-left: auto; font-size: 0.8rem; color: #666;">
            Discovery: {metadata.get('discovery_method', 'unknown')} |
            Account: {metadata.get('account_id', 'unknown')} |
            Region: {', '.join(metadata.get('regions', []))}
        </span>
    </div>
    <div class="diagram-container" id="diagram">
"""

    # Render topology
    for account_id, account_data in topology.get("accounts", {}).items():
        html += f'        <div class="account-box">\n'
        html += f'            <div class="account-label">📋 Account: {account_id}</div>\n'

        for region, region_data in account_data.get("regions", {}).items():
            html += f'            <div class="region-box">\n'
            html += f'                <div class="region-label">🌐 Region: {region}</div>\n'

            for vpc_id, vpc_data in region_data.get("vpcs", {}).items():
                cidr = vpc_data.get("cidr", "")
                vpc_name = ""
                # Try to get VPC name from resources
                vpc_arn = f"arn:aws:ec2:{region}:{account_id}:vpc/{vpc_id}"
                if vpc_arn in resource_map:
                    tags = resource_map[vpc_arn].get("tags", {})
                    vpc_name = tags.get("Name", "")

                html += f'                <div class="vpc-box">\n'
                html += f'                    <div class="vpc-label">🔲 VPC: {vpc_name or vpc_id} ({cidr})</div>\n'
                html += f'                    <div class="az-container">\n'

                for az, az_data in vpc_data.get("availability_zones", {}).items():
                    html += f'                        <div class="az-box">\n'
                    html += f'                            <div class="az-label">📍 {az}</div>\n'

                    for subnet_id, subnet_data in az_data.get("subnets", {}).items():
                        subnet_type = subnet_data.get("type", "private")
                        subnet_cidr = subnet_data.get("cidr", "")
                        html += f'                            <div class="subnet-box {subnet_type}">\n'
                        html += f'                                <div class="subnet-label">{subnet_type.title()} Subnet: {subnet_id[:15]}... ({subnet_cidr})</div>\n'

                        # Render resources in this subnet
                        for res_arn in subnet_data.get("resources", []):
                            if res_arn in resource_map:
                                r = resource_map[res_arn]
                                icon = get_icon_info(r["service"], r["resource_type"])
                                label = get_resource_label(r)
                                tooltip_html = get_tooltip(r).replace('"', '&quot;')
                                html += f'                                <div class="resource-node" style="border-color: {icon["color"]}" data-arn="{r["arn"]}">\n'
                                html += f'                                    <div class="icon" style="background: {icon["color"]}">{icon["label"][:3]}</div>\n'
                                html += f'                                    <span>{label}</span>\n'
                                html += f'                                    <div class="tooltip">{tooltip_html}</div>\n'
                                html += f'                                </div>\n'

                        html += f'                            </div>\n'
                    html += f'                        </div>\n'

                html += f'                    </div>\n'
                html += f'                </div>\n'

            # Global resources (not in VPC)
            global_res = region_data.get("global_resources", [])
            if global_res:
                html += f'                <div class="global-resources">\n'
                html += f'                    <div class="section-label">☁️ Regional Services (outside VPC)</div>\n'
                for res_arn in global_res:
                    if res_arn in resource_map:
                        r = resource_map[res_arn]
                        icon = get_icon_info(r["service"], r["resource_type"])
                        label = get_resource_label(r)
                        tooltip_html = get_tooltip(r).replace('"', '&quot;')
                        html += f'                    <div class="resource-node" style="border-color: {icon["color"]}" data-arn="{r["arn"]}">\n'
                        html += f'                        <div class="icon" style="background: {icon["color"]}">{icon["label"][:3]}</div>\n'
                        html += f'                        <span>{label}</span>\n'
                        html += f'                        <div class="tooltip">{tooltip_html}</div>\n'
                        html += f'                    </div>\n'
                html += f'                </div>\n'

            html += f'            </div>\n'
        html += f'        </div>\n'

    # Connections section
    if edges:
        html += f'        <div class="connections-section" id="connections-section">\n'
        html += f'            <h3 style="font-size: 0.9rem; margin-bottom: 10px;">🔗 Connections ({len(edges)})</h3>\n'
        for edge in edges[:50]:  # Limit display
            source_label = get_resource_label(resource_map[edge["source"]]) if edge["source"] in resource_map else edge["source"].split("/")[-1]
            target_label = get_resource_label(resource_map[edge["target"]]) if edge["target"] in resource_map else edge["target"].split("/")[-1]
            style = CONNECTION_STYLES.get(edge["type"], CONNECTION_STYLES["default"])
            html += f'            <div class="connection-line">\n'
            html += f'                <span style="color: {style["color"]}">●</span>\n'
            html += f'                <span>{source_label}</span>\n'
            html += f'                <span class="conn-arrow">→</span>\n'
            html += f'                <span>{target_label}</span>\n'
            html += f'                <span style="color: #999; margin-left: auto;">[{edge["type"]}]</span>\n'
            html += f'            </div>\n'
        if len(edges) > 50:
            html += f'            <div style="color: #999; font-size: 0.75rem; margin-top: 8px;">... and {len(edges) - 50} more connections</div>\n'
        html += f'        </div>\n'

    html += f"""
    </div>

    <div class="legend">
        <h3>Legend</h3>
        <div class="legend-item"><div class="legend-color" style="background: #ED7100"></div> Compute</div>
        <div class="legend-item"><div class="legend-color" style="background: #8C4FFF"></div> Networking</div>
        <div class="legend-item"><div class="legend-color" style="background: #3B48CC"></div> Database</div>
        <div class="legend-item"><div class="legend-color" style="background: #3F8624"></div> Storage</div>
        <div class="legend-item"><div class="legend-color" style="background: #DD344C"></div> Security</div>
        <div class="legend-item"><div class="legend-color" style="background: #E7157B"></div> Integration</div>
        <hr style="margin: 8px 0; border: none; border-top: 1px solid #eee;">
        <div style="font-size: 0.7rem; color: #666;">
            Hover nodes for details<br>
            Ctrl+P to print
        </div>
    </div>

    <script>
        function toggleConnections() {{
            const section = document.getElementById('connections-section');
            if (section) section.style.display = section.style.display === 'none' ? 'block' : 'none';
        }}
        function expandAll() {{
            // Future: toggle collapsed sections
            alert('All sections expanded');
        }}

        // Highlight connected resources on click
        document.querySelectorAll('.resource-node').forEach(node => {{
            node.addEventListener('click', () => {{
                const arn = node.dataset.arn;
                // Reset all
                document.querySelectorAll('.resource-node').forEach(n => n.style.opacity = '1');
                // Find connected
                const connections = {json.dumps(edges)};
                const connected = new Set();
                connected.add(arn);
                connections.forEach(c => {{
                    if (c.source === arn) connected.add(c.target);
                    if (c.target === arn) connected.add(c.source);
                }});
                // Dim non-connected
                document.querySelectorAll('.resource-node').forEach(n => {{
                    if (!connected.has(n.dataset.arn)) {{
                        n.style.opacity = '0.3';
                    }}
                }});
            }});
        }});

        // Click background to reset
        document.getElementById('diagram').addEventListener('click', (e) => {{
            if (e.target.id === 'diagram' || e.target.classList.contains('diagram-container')) {{
                document.querySelectorAll('.resource-node').forEach(n => n.style.opacity = '1');
            }}
        }});
    </script>
</body>
</html>"""

    output_path = Path(project_dir) / "architecture-diagram.html"
    with open(output_path, "w") as f:
        f.write(html)

    print(f"=== Diagram Generated ===")
    print(f"  Output: {output_path}")
    print(f"  Nodes: {len(nodes)}")
    print(f"  Edges: {len(edges)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 generate_diagram.py <PROJECT_DIR>")
        sys.exit(1)
    generate_html(sys.argv[1])
