#!/bin/bash
# discover_by_tag.sh — Discover AWS resources by tag key/value
# Usage: ./discover_by_tag.sh <TAG_KEY> <TAG_VALUE> <REGION> <PROFILE> <OUTPUT_DIR>

set -euo pipefail

TAG_KEY="${1:?Usage: $0 <TAG_KEY> <TAG_VALUE> <REGION> <PROFILE> <OUTPUT_DIR>}"
TAG_VALUE="${2:?Missing TAG_VALUE}"
REGION="${3:?Missing REGION}"
PROFILE="${4:-default}"
OUTPUT_DIR="${5:?Missing OUTPUT_DIR}"

mkdir -p "$OUTPUT_DIR"

echo "=== Infrastructure Harvest: Discovery by Tag ==="
echo "Tag: $TAG_KEY=$TAG_VALUE"
echo "Region: $REGION"
echo "Profile: $PROFILE"
echo ""

# Step 0: Verify credentials
echo "[1/4] Verifying AWS credentials..."
IDENTITY=$(aws sts get-caller-identity --profile "$PROFILE" --region "$REGION" --output json 2>&1)
if [ $? -ne 0 ]; then
    echo "ERROR: AWS CLI authentication failed. Please check your credentials."
    echo "$IDENTITY"
    exit 1
fi
ACCOUNT_ID=$(echo "$IDENTITY" | python3 -c "import sys,json; print(json.load(sys.stdin)['Account'])")
echo "  Account: $ACCOUNT_ID"
echo ""

# Step 1: Query Resource Groups Tagging API
echo "[2/4] Discovering resources with tag $TAG_KEY=$TAG_VALUE..."
RESOURCES_FILE="$OUTPUT_DIR/tag_resources_raw.json"

aws resourcegroupstaggingapi get-resources \
    --tag-filters "Key=$TAG_KEY,Values=$TAG_VALUE" \
    --region "$REGION" \
    --profile "$PROFILE" \
    --no-paginate \
    --output json > "$RESOURCES_FILE" 2>&1

RESOURCE_COUNT=$(python3 -c "
import json
with open('$RESOURCES_FILE') as f:
    data = json.load(f)
    resources = data.get('ResourceTagMappingList', [])
    print(len(resources))
")
echo "  Found $RESOURCE_COUNT tagged resources"
echo ""

# Step 2: Extract unique VPC IDs from EC2 resources for expansion
echo "[3/4] Identifying VPCs for expansion..."
VPC_IDS=$(python3 -c "
import json
with open('$RESOURCES_FILE') as f:
    data = json.load(f)
resources = data.get('ResourceTagMappingList', [])
# Extract resource types
vpcs = set()
ec2_ids = []
for r in resources:
    arn = r['ResourceARN']
    parts = arn.split(':')
    if len(parts) >= 6:
        service = parts[2]
        resource = ':'.join(parts[5:])
        if service == 'ec2' and resource.startswith('vpc/'):
            vpcs.add(resource.split('/')[1])
        elif service == 'ec2' and resource.startswith('instance/'):
            ec2_ids.append(resource.split('/')[1])
# Print VPC IDs
for v in vpcs:
    print(v)
")

# If we found EC2 instances but no direct VPC tags, get VPCs from instances
if [ -z "$VPC_IDS" ]; then
    EC2_IDS=$(python3 -c "
import json
with open('$RESOURCES_FILE') as f:
    data = json.load(f)
resources = data.get('ResourceTagMappingList', [])
ids = []
for r in resources:
    arn = r['ResourceARN']
    parts = arn.split(':')
    if len(parts) >= 6 and parts[2] == 'ec2' and ':'.join(parts[5:]).startswith('instance/'):
        ids.append(':'.join(parts[5:]).split('/')[1])
print(' '.join(ids))
")
    if [ -n "$EC2_IDS" ]; then
        VPC_IDS=$(aws ec2 describe-instances \
            --instance-ids $EC2_IDS \
            --region "$REGION" \
            --profile "$PROFILE" \
            --query "Reservations[].Instances[].VpcId" \
            --output text 2>/dev/null | tr '\t' '\n' | sort -u)
    fi
fi

echo "  VPCs identified: $(echo "$VPC_IDS" | grep -c . || echo 0)"

# Step 3: Build discovery.json
echo "[4/4] Building discovery manifest..."
python3 -c "
import json, sys
from datetime import datetime

with open('$RESOURCES_FILE') as f:
    data = json.load(f)

resources = []
for r in data.get('ResourceTagMappingList', []):
    arn = r['ResourceARN']
    parts = arn.split(':')
    service = parts[2] if len(parts) > 2 else 'unknown'
    region = parts[3] if len(parts) > 3 else '$REGION'
    account = parts[4] if len(parts) > 4 else '$ACCOUNT_ID'
    resource_part = ':'.join(parts[5:]) if len(parts) > 5 else ''

    # Parse resource type and ID
    if '/' in resource_part:
        resource_type, resource_id = resource_part.split('/', 1)
    elif ':' in resource_part:
        resource_type, resource_id = resource_part.split(':', 1)
    else:
        resource_type = resource_part
        resource_id = resource_part

    tags = {t['Key']: t['Value'] for t in r.get('Tags', [])}

    resources.append({
        'arn': arn,
        'service': service,
        'resource_type': resource_type,
        'resource_id': resource_id,
        'region': region or '$REGION',
        'account_id': account or '$ACCOUNT_ID',
        'tags': tags,
        'discovery_source': 'tag-query'
    })

output = {
    'metadata': {
        'discovery_method': 'tag',
        'tag_key': '$TAG_KEY',
        'tag_value': '$TAG_VALUE',
        'regions': ['$REGION'],
        'profile': '$PROFILE',
        'account_id': '$ACCOUNT_ID',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'vpc_ids': [v for v in '''$VPC_IDS'''.strip().split('\n') if v]
    },
    'resources': resources
}

output_path = '$OUTPUT_DIR/discovery.json'
with open(output_path, 'w') as f:
    json.dump(output, f, indent=2)
print(f'  Written: {output_path}')
print(f'  Total resources: {len(resources)}')
"

echo ""
echo "=== Discovery Complete ==="
echo "Output: $OUTPUT_DIR/discovery.json"
echo ""
echo "Next: Run enrich_resources.sh to gather detailed configurations."
