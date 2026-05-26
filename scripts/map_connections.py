#!/usr/bin/env python3
"""
map_connections.py — Map relationships between discovered AWS resources.
Usage: python3 map_connections.py <PROJECT_DIR>
"""

import json
import sys
from pathlib import Path


def map_connections(project_dir: str):
    """Analyze enriched resources and map connections between them."""
    enriched_path = Path(project_dir) / "enriched.json"
    if not enriched_path.exists():
        print(f"ERROR: {enriched_path} not found. Run enrichment first.")
        sys.exit(1)

    with open(enriched_path) as f:
        data = json.load(f)

    resources = data["resources"]
    connections = []
    topology = {"accounts": {}}

    # Build lookup maps
    arn_map = {r["arn"]: r for r in resources}
    id_map = {r["resource_id"]: r for r in resources}
    sg_map = {}  # sg_id -> [resource_arns]
    vpc_resources = {}  # vpc_id -> [resources]
    subnet_resources = {}  # subnet_id -> [resources]

    print(f"Mapping connections for {len(resources)} resources...")

    # Pass 1: Build indexes
    for r in resources:
        details = r.get("details") or {}
        rid = r["resource_id"]

        # Track VPC membership
        vpc_id = details.get("vpc_id")
        if not vpc_id and r["resource_type"] == "vpc":
            vpc_id = rid
        if vpc_id:
            vpc_resources.setdefault(vpc_id, []).append(r)

        # Track subnet membership
        subnet_id = details.get("subnet_id")
        if subnet_id:
            subnet_resources.setdefault(subnet_id, []).append(r)

        # Track security group membership
        sgs = details.get("security_groups", [])
        if isinstance(sgs, list):
            for sg in sgs:
                sg_id = sg["id"] if isinstance(sg, dict) else sg
                sg_map.setdefault(sg_id, []).append(r["arn"])

    # Pass 2: Map connections
    for r in resources:
        details = r.get("details") or {}
        service = r["service"]
        rtype = r["resource_type"]

        # VPC membership connections
        vpc_id = details.get("vpc_id")
        if vpc_id and rtype != "vpc":
            vpc_arn = f"arn:aws:ec2:{r['region']}:{r['account_id']}:vpc/{vpc_id}"
            connections.append({
                "source_arn": r["arn"],
                "target_arn": vpc_arn,
                "connection_type": "vpc-membership",
                "details": {"relationship": "resides-in"}
            })

        # Subnet membership
        subnet_id = details.get("subnet_id")
        if subnet_id and rtype not in ("subnet", "vpc"):
            subnet_arn = f"arn:aws:ec2:{r['region']}:{r['account_id']}:subnet/{subnet_id}"
            connections.append({
                "source_arn": r["arn"],
                "target_arn": subnet_arn,
                "connection_type": "subnet-membership",
                "details": {"relationship": "resides-in"}
            })

        # Security group ingress (SG-to-SG references)
        if rtype in ("security-group", "sg"):
            inbound = details.get("inbound_rules", [])
            for rule in inbound:
                sources = rule.get("sources", [])
                for src in sources:
                    if src.startswith("sg-"):
                        # This SG allows inbound from another SG
                        src_arn = f"arn:aws:ec2:{r['region']}:{r['account_id']}:security-group/{src}"
                        connections.append({
                            "source_arn": src_arn,
                            "target_arn": r["arn"],
                            "connection_type": "security-group-ingress",
                            "details": {
                                "protocol": rule.get("protocol"),
                                "from_port": rule.get("from_port"),
                                "to_port": rule.get("to_port"),
                                "direction": "inbound"
                            }
                        })

        # Load balancer → target groups
        if service == "elasticloadbalancing":
            target_groups = details.get("target_groups", [])
            for tg in target_groups:
                connections.append({
                    "source_arn": r["arn"],
                    "target_arn": tg["arn"],
                    "connection_type": "load-balancer-target",
                    "details": {
                        "protocol": tg.get("protocol"),
                        "port": tg.get("port"),
                        "target_type": tg.get("target_type")
                    }
                })

        # Lambda VPC connection
        if service == "lambda":
            vpc_config = details.get("vpc_config", {})
            if vpc_config and vpc_config.get("VpcId"):
                lambda_vpc = vpc_config["VpcId"]
                vpc_arn = f"arn:aws:ec2:{r['region']}:{r['account_id']}:vpc/{lambda_vpc}"
                connections.append({
                    "source_arn": r["arn"],
                    "target_arn": vpc_arn,
                    "connection_type": "lambda-vpc",
                    "details": {
                        "subnet_ids": vpc_config.get("SubnetIds", []),
                        "security_group_ids": vpc_config.get("SecurityGroupIds", [])
                    }
                })

        # NAT Gateway → subnet (public)
        if rtype == "natgateway":
            nat_subnet = details.get("subnet_id")
            if nat_subnet:
                subnet_arn = f"arn:aws:ec2:{r['region']}:{r['account_id']}:subnet/{nat_subnet}"
                connections.append({
                    "source_arn": r["arn"],
                    "target_arn": subnet_arn,
                    "connection_type": "nat-placement",
                    "details": {"relationship": "placed-in-public-subnet"}
                })

    # Pass 3: Build topology
    for r in resources:
        account_id = r["account_id"]
        region = r["region"]
        details = r.get("details") or {}

        # Ensure account/region structure
        if account_id not in topology["accounts"]:
            topology["accounts"][account_id] = {"regions": {}}
        if region not in topology["accounts"][account_id]["regions"]:
            topology["accounts"][account_id]["regions"][region] = {
                "vpcs": {},
                "global_resources": []
            }

        region_data = topology["accounts"][account_id]["regions"][region]

        # Place in VPC topology
        vpc_id = details.get("vpc_id")
        if r["resource_type"] == "vpc":
            vpc_id = r["resource_id"]

        if vpc_id:
            if vpc_id not in region_data["vpcs"]:
                region_data["vpcs"][vpc_id] = {
                    "cidr": details.get("cidr_block", ""),
                    "availability_zones": {}
                }

            # Place in AZ/subnet
            az = details.get("availability_zone", "")
            subnet_id = details.get("subnet_id", "")

            if az and r["resource_type"] not in ("vpc", "subnet"):
                if az not in region_data["vpcs"][vpc_id]["availability_zones"]:
                    region_data["vpcs"][vpc_id]["availability_zones"][az] = {"subnets": {}}

                az_data = region_data["vpcs"][vpc_id]["availability_zones"][az]
                if subnet_id:
                    if subnet_id not in az_data["subnets"]:
                        # Determine if public or private
                        subnet_details = id_map.get(subnet_id, {}).get("details", {})
                        is_public = subnet_details.get("map_public_ip", False)
                        az_data["subnets"][subnet_id] = {
                            "cidr": subnet_details.get("cidr_block", ""),
                            "type": "public" if is_public else "private",
                            "resources": []
                        }
                    az_data["subnets"][subnet_id]["resources"].append(r["arn"])
            elif r["resource_type"] == "subnet":
                az = details.get("availability_zone", "unknown-az")
                if az not in region_data["vpcs"][vpc_id]["availability_zones"]:
                    region_data["vpcs"][vpc_id]["availability_zones"][az] = {"subnets": {}}
                az_data = region_data["vpcs"][vpc_id]["availability_zones"][az]
                is_public = details.get("map_public_ip", False)
                if r["resource_id"] not in az_data["subnets"]:
                    az_data["subnets"][r["resource_id"]] = {
                        "cidr": details.get("cidr_block", ""),
                        "type": "public" if is_public else "private",
                        "resources": []
                    }
        else:
            # Global/regional resource (S3, CloudFront, etc.)
            if r["resource_type"] not in ("route-table", "internet-gateway"):
                region_data["global_resources"].append(r["arn"])

    # Deduplicate connections
    seen = set()
    unique_connections = []
    for c in connections:
        key = (c["source_arn"], c["target_arn"], c["connection_type"])
        if key not in seen:
            seen.add(key)
            unique_connections.append(c)

    output = {
        "metadata": data["metadata"],
        "connections": unique_connections,
        "topology": topology,
        "stats": {
            "total_connections": len(unique_connections),
            "connection_types": {}
        }
    }

    # Count by type
    for c in unique_connections:
        ctype = c["connection_type"]
        output["stats"]["connection_types"][ctype] = output["stats"]["connection_types"].get(ctype, 0) + 1

    output_path = Path(project_dir) / "connections.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n=== Connection Mapping Complete ===")
    print(f"  Total connections: {len(unique_connections)}")
    print(f"  Connection types:")
    for ctype, count in sorted(output["stats"]["connection_types"].items()):
        print(f"    {ctype}: {count}")
    print(f"  Accounts: {len(topology['accounts'])}")
    total_vpcs = sum(
        len(reg["vpcs"])
        for acct in topology["accounts"].values()
        for reg in acct["regions"].values()
    )
    print(f"  VPCs: {total_vpcs}")
    print(f"  Output: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 map_connections.py <PROJECT_DIR>")
        sys.exit(1)
    map_connections(sys.argv[1])
