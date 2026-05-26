#!/bin/bash
# discover_by_arn.sh — Discover AWS resources starting from a known ARN
# Usage: ./discover_by_arn.sh <ARN> <REGION> <PROFILE> <OUTPUT_DIR>

set -euo pipefail

ARN="${1:?Usage: $0 <ARN> <REGION> <PROFILE> <OUTPUT_DIR>}"
REGION="${2:?Missing REGION}"
PROFILE="${3:-default}"
OUTPUT_DIR="${4:?Missing OUTPUT_DIR}"

mkdir -p "$OUTPUT_DIR"

echo "=== Infrastructure Harvest: Discovery by ARN ==="
echo "Starting ARN: $ARN"
echo "Region: $REGION"
echo "Profile: $PROFILE"
echo ""

# Verify credentials
echo "[1/3] Verifying AWS credentials..."
IDENTITY=$(aws sts get-caller-identity --profile "$PROFILE" --region "$REGION" --output json 2>&1)
if [ $? -ne 0 ]; then
    echo "ERROR: AWS CLI authentication failed."
    echo "$IDENTITY"
    exit 1
fi
ACCOUNT_ID=$(echo "$IDENTITY" | python3 -c "import sys,json; print(json.load(sys.stdin)['Account'])")
echo "  Account: $ACCOUNT_ID"
echo ""

# Parse the ARN to determine service and resource type
echo "[2/3] Parsing ARN and discovering related resources..."
python3 << 'PYTHON_SCRIPT'
import json
import subprocess
import sys
from datetime import datetime

ARN = "$ARN"
REGION = "$REGION"
PROFILE = "$PROFILE"
ACCOUNT_ID = "$ACCOUNT_ID"
OUTPUT_DIR = "$OUTPUT_DIR"

def run_aws_cmd(cmd):
    """Run an AWS CLI command and return parsed JSON."""
    full_cmd = f"{cmd} --region {REGION} --profile {PROFILE} --output json"
    try:
        result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            print(f"  WARN: {cmd.split()[0:4]} failed: {result.stderr.strip()[:100]}", file=sys.stderr)
            return None
    except (json.JSONDecodeError, subprocess.TimeoutExpired) as e:
        print(f"  WARN: {e}", file=sys.stderr)
        return None

def parse_arn(arn):
    """Parse ARN into components."""
    parts = arn.split(':')
    return {
        'partition': parts[1] if len(parts) > 1 else 'aws',
        'service': parts[2] if len(parts) > 2 else '',
        'region': parts[3] if len(parts) > 3 else '',
        'account': parts[4] if len(parts) > 4 else '',
        'resource': ':'.join(parts[5:]) if len(parts) > 5 else ''
    }

def discover_from_vpc(vpc_id):
    """Discover all resources within a VPC."""
    resources = []

    # Subnets
    data = run_aws_cmd(f"aws ec2 describe-subnets --filters Name=vpc-id,Values={vpc_id}")
    if data:
        for s in data.get('Subnets', []):
            resources.append({
                'arn': f"arn:aws:ec2:{REGION}:{ACCOUNT_ID}:subnet/{s['SubnetId']}",
                'service': 'ec2', 'resource_type': 'subnet',
                'resource_id': s['SubnetId'], 'region': REGION,
                'account_id': ACCOUNT_ID,
                'tags': {t['Key']: t['Value'] for t in s.get('Tags', [])},
                'discovery_source': 'vpc-expansion'
            })

    # Security Groups
    data = run_aws_cmd(f"aws ec2 describe-security-groups --filters Name=vpc-id,Values={vpc_id}")
    if data:
        for sg in data.get('SecurityGroups', []):
            resources.append({
                'arn': f"arn:aws:ec2:{REGION}:{ACCOUNT_ID}:security-group/{sg['GroupId']}",
                'service': 'ec2', 'resource_type': 'security-group',
                'resource_id': sg['GroupId'], 'region': REGION,
                'account_id': ACCOUNT_ID,
                'tags': {t['Key']: t['Value'] for t in sg.get('Tags', [])},
                'discovery_source': 'vpc-expansion'
            })

    # EC2 Instances
    data = run_aws_cmd(f"aws ec2 describe-instances --filters Name=vpc-id,Values={vpc_id}")
    if data:
        for r in data.get('Reservations', []):
            for i in r.get('Instances', []):
                resources.append({
                    'arn': f"arn:aws:ec2:{REGION}:{ACCOUNT_ID}:instance/{i['InstanceId']}",
                    'service': 'ec2', 'resource_type': 'instance',
                    'resource_id': i['InstanceId'], 'region': REGION,
                    'account_id': ACCOUNT_ID,
                    'tags': {t['Key']: t['Value'] for t in i.get('Tags', [])},
                    'discovery_source': 'vpc-expansion'
                })

    # NAT Gateways
    data = run_aws_cmd(f"aws ec2 describe-nat-gateways --filter Name=vpc-id,Values={vpc_id}")
    if data:
        for ng in data.get('NatGateways', []):
            resources.append({
                'arn': f"arn:aws:ec2:{REGION}:{ACCOUNT_ID}:natgateway/{ng['NatGatewayId']}",
                'service': 'ec2', 'resource_type': 'natgateway',
                'resource_id': ng['NatGatewayId'], 'region': REGION,
                'account_id': ACCOUNT_ID,
                'tags': {t['Key']: t['Value'] for t in ng.get('Tags', [])},
                'discovery_source': 'vpc-expansion'
            })

    # Internet Gateways
    data = run_aws_cmd(f"aws ec2 describe-internet-gateways --filters Name=attachment.vpc-id,Values={vpc_id}")
    if data:
        for igw in data.get('InternetGateways', []):
            resources.append({
                'arn': f"arn:aws:ec2:{REGION}:{ACCOUNT_ID}:internet-gateway/{igw['InternetGatewayId']}",
                'service': 'ec2', 'resource_type': 'internet-gateway',
                'resource_id': igw['InternetGatewayId'], 'region': REGION,
                'account_id': ACCOUNT_ID,
                'tags': {t['Key']: t['Value'] for t in igw.get('Tags', [])},
                'discovery_source': 'vpc-expansion'
            })

    # Route Tables
    data = run_aws_cmd(f"aws ec2 describe-route-tables --filters Name=vpc-id,Values={vpc_id}")
    if data:
        for rt in data.get('RouteTables', []):
            resources.append({
                'arn': f"arn:aws:ec2:{REGION}:{ACCOUNT_ID}:route-table/{rt['RouteTableId']}",
                'service': 'ec2', 'resource_type': 'route-table',
                'resource_id': rt['RouteTableId'], 'region': REGION,
                'account_id': ACCOUNT_ID,
                'tags': {t['Key']: t['Value'] for t in rt.get('Tags', [])},
                'discovery_source': 'vpc-expansion'
            })

    return resources

# Main logic
parsed = parse_arn(ARN)
resources = []
vpc_ids = set()

# Add the starting resource
resource_part = parsed['resource']
if '/' in resource_part:
    resource_type, resource_id = resource_part.split('/', 1)
elif ':' in resource_part:
    resource_type, resource_id = resource_part.split(':', 1)
else:
    resource_type = resource_part
    resource_id = resource_part

resources.append({
    'arn': ARN,
    'service': parsed['service'],
    'resource_type': resource_type,
    'resource_id': resource_id,
    'region': parsed['region'] or REGION,
    'account_id': parsed['account'] or ACCOUNT_ID,
    'tags': {},
    'discovery_source': 'arn-direct'
})

# Discover based on resource type
if parsed['service'] == 'ec2' and resource_type == 'vpc':
    vpc_ids.add(resource_id)
elif parsed['service'] == 'ec2' and resource_type == 'instance':
    # Get VPC from instance
    data = run_aws_cmd(f"aws ec2 describe-instances --instance-ids {resource_id}")
    if data:
        for r in data.get('Reservations', []):
            for i in r.get('Instances', []):
                vpc_id = i.get('VpcId')
                if vpc_id:
                    vpc_ids.add(vpc_id)
elif parsed['service'] == 'elasticloadbalancing':
    # Get VPC from load balancer
    data = run_aws_cmd(f"aws elbv2 describe-load-balancers --load-balancer-arns {ARN}")
    if data:
        for lb in data.get('LoadBalancers', []):
            vpc_id = lb.get('VpcId')
            if vpc_id:
                vpc_ids.add(vpc_id)
elif parsed['service'] == 'rds':
    data = run_aws_cmd(f"aws rds describe-db-instances --db-instance-identifier {resource_id}")
    if data:
        for db in data.get('DBInstances', []):
            subnet_group = db.get('DBSubnetGroup', {})
            vpc_id = subnet_group.get('VpcId')
            if vpc_id:
                vpc_ids.add(vpc_id)

# Expand VPCs
for vpc_id in vpc_ids:
    print(f"  Expanding VPC: {vpc_id}")
    vpc_resources = discover_from_vpc(vpc_id)
    resources.extend(vpc_resources)
    # Add VPC itself
    resources.append({
        'arn': f"arn:aws:ec2:{REGION}:{ACCOUNT_ID}:vpc/{vpc_id}",
        'service': 'ec2', 'resource_type': 'vpc',
        'resource_id': vpc_id, 'region': REGION,
        'account_id': ACCOUNT_ID, 'tags': {},
        'discovery_source': 'arn-relation'
    })

# Deduplicate by ARN
seen = set()
unique_resources = []
for r in resources:
    if r['arn'] not in seen:
        seen.add(r['arn'])
        unique_resources.append(r)

# Write output
output = {
    'metadata': {
        'discovery_method': 'arn',
        'starting_arn': ARN,
        'regions': [REGION],
        'profile': PROFILE,
        'account_id': ACCOUNT_ID,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'vpc_ids': list(vpc_ids)
    },
    'resources': unique_resources
}

output_path = f"{OUTPUT_DIR}/discovery.json"
with open(output_path, 'w') as f:
    json.dump(output, f, indent=2)

print(f"  Discovered {len(unique_resources)} unique resources")
print(f"  VPCs found: {len(vpc_ids)}")
PYTHON_SCRIPT

echo ""
echo "[3/3] Discovery complete."
echo "Output: $OUTPUT_DIR/discovery.json"
echo ""
echo "Next: Run enrich_resources.sh to gather detailed configurations."
