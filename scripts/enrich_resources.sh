#!/bin/bash
# enrich_resources.sh — Enrich discovered resources with detailed configurations
# Usage: ./enrich_resources.sh <PROJECT_DIR> <REGION> <PROFILE>

set -euo pipefail

PROJECT_DIR="${1:?Usage: $0 <PROJECT_DIR> <REGION> <PROFILE>}"
REGION="${2:?Missing REGION}"
PROFILE="${3:-default}"

DISCOVERY_FILE="$PROJECT_DIR/discovery.json"
OUTPUT_FILE="$PROJECT_DIR/enriched.json"

if [ ! -f "$DISCOVERY_FILE" ]; then
    echo "ERROR: $DISCOVERY_FILE not found. Run discovery first."
    exit 1
fi

echo "=== Infrastructure Harvest: Enrichment ==="
echo "Input: $DISCOVERY_FILE"
echo "Region: $REGION"
echo "Profile: $PROFILE"
echo ""

python3 << 'PYTHON_SCRIPT'
import json
import subprocess
import sys
import time
from datetime import datetime

PROJECT_DIR = "$PROJECT_DIR"
REGION = "$REGION"
PROFILE = "$PROFILE"

def run_aws(cmd):
    """Run AWS CLI command, return parsed JSON or None."""
    full_cmd = f"{cmd} --region {REGION} --profile {PROFILE} --output json"
    try:
        result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
        return None
    except (json.JSONDecodeError, subprocess.TimeoutExpired):
        return None

def enrich_ec2_instance(resource_id):
    data = run_aws(f"aws ec2 describe-instances --instance-ids {resource_id}")
    if data and data.get('Reservations'):
        inst = data['Reservations'][0]['Instances'][0]
        return {
            'instance_type': inst.get('InstanceType'),
            'state': inst.get('State', {}).get('Name'),
            'vpc_id': inst.get('VpcId'),
            'subnet_id': inst.get('SubnetId'),
            'private_ip': inst.get('PrivateIpAddress'),
            'public_ip': inst.get('PublicIpAddress'),
            'security_groups': [{'id': sg['GroupId'], 'name': sg['GroupName']} for sg in inst.get('SecurityGroups', [])],
            'iam_profile': inst.get('IamInstanceProfile', {}).get('Arn'),
            'platform': inst.get('PlatformDetails'),
            'launch_time': inst.get('LaunchTime'),
            'availability_zone': inst.get('Placement', {}).get('AvailabilityZone')
        }
    return None

def enrich_vpc(resource_id):
    data = run_aws(f"aws ec2 describe-vpcs --vpc-ids {resource_id}")
    if data and data.get('Vpcs'):
        vpc = data['Vpcs'][0]
        return {
            'cidr_block': vpc.get('CidrBlock'),
            'cidr_blocks': [a['CidrBlock'] for a in vpc.get('CidrBlockAssociationSet', [])],
            'is_default': vpc.get('IsDefault'),
            'state': vpc.get('State'),
            'dhcp_options_id': vpc.get('DhcpOptionsId')
        }
    return None

def enrich_subnet(resource_id):
    data = run_aws(f"aws ec2 describe-subnets --subnet-ids {resource_id}")
    if data and data.get('Subnets'):
        subnet = data['Subnets'][0]
        return {
            'cidr_block': subnet.get('CidrBlock'),
            'vpc_id': subnet.get('VpcId'),
            'availability_zone': subnet.get('AvailabilityZone'),
            'available_ips': subnet.get('AvailableIpAddressCount'),
            'map_public_ip': subnet.get('MapPublicIpOnLaunch'),
            'state': subnet.get('State')
        }
    return None

def enrich_security_group(resource_id):
    data = run_aws(f"aws ec2 describe-security-groups --group-ids {resource_id}")
    if data and data.get('SecurityGroups'):
        sg = data['SecurityGroups'][0]
        return {
            'group_name': sg.get('GroupName'),
            'description': sg.get('Description'),
            'vpc_id': sg.get('VpcId'),
            'inbound_rules': [{
                'protocol': r.get('IpProtocol'),
                'from_port': r.get('FromPort'),
                'to_port': r.get('ToPort'),
                'sources': [ip['CidrIp'] for ip in r.get('IpRanges', [])] +
                          [sg['GroupId'] for sg in r.get('UserIdGroupPairs', [])]
            } for r in sg.get('IpPermissions', [])],
            'outbound_rules': [{
                'protocol': r.get('IpProtocol'),
                'from_port': r.get('FromPort'),
                'to_port': r.get('ToPort'),
                'destinations': [ip['CidrIp'] for ip in r.get('IpRanges', [])] +
                               [sg['GroupId'] for sg in r.get('UserIdGroupPairs', [])]
            } for r in sg.get('IpPermissionsEgress', [])]
        }
    return None

def enrich_rds(resource_id):
    data = run_aws(f"aws rds describe-db-instances --db-instance-identifier {resource_id}")
    if data and data.get('DBInstances'):
        db = data['DBInstances'][0]
        return {
            'engine': db.get('Engine'),
            'engine_version': db.get('EngineVersion'),
            'instance_class': db.get('DBInstanceClass'),
            'multi_az': db.get('MultiAZ'),
            'storage_type': db.get('StorageType'),
            'allocated_storage_gb': db.get('AllocatedStorage'),
            'endpoint': db.get('Endpoint', {}).get('Address'),
            'port': db.get('Endpoint', {}).get('Port'),
            'vpc_security_groups': [sg['VpcSecurityGroupId'] for sg in db.get('VpcSecurityGroups', [])],
            'subnet_group': db.get('DBSubnetGroup', {}).get('DBSubnetGroupName'),
            'vpc_id': db.get('DBSubnetGroup', {}).get('VpcId'),
            'availability_zone': db.get('AvailabilityZone'),
            'status': db.get('DBInstanceStatus')
        }
    return None

def enrich_lambda(resource_id):
    data = run_aws(f"aws lambda get-function --function-name {resource_id}")
    if data:
        config = data.get('Configuration', {})
        return {
            'runtime': config.get('Runtime'),
            'memory_mb': config.get('MemorySize'),
            'timeout': config.get('Timeout'),
            'handler': config.get('Handler'),
            'code_size_bytes': config.get('CodeSize'),
            'vpc_config': config.get('VpcConfig'),
            'layers': [l['Arn'] for l in config.get('Layers', [])],
            'environment_keys': list(config.get('Environment', {}).get('Variables', {}).keys()),
            'state': config.get('State'),
            'last_modified': config.get('LastModified')
        }
    return None

def enrich_elb(arn):
    data = run_aws(f"aws elbv2 describe-load-balancers --load-balancer-arns {arn}")
    if data and data.get('LoadBalancers'):
        lb = data['LoadBalancers'][0]
        # Get target groups
        tg_data = run_aws(f"aws elbv2 describe-target-groups --load-balancer-arn {arn}")
        target_groups = []
        if tg_data:
            for tg in tg_data.get('TargetGroups', []):
                target_groups.append({
                    'arn': tg['TargetGroupArn'],
                    'name': tg['TargetGroupName'],
                    'protocol': tg.get('Protocol'),
                    'port': tg.get('Port'),
                    'target_type': tg.get('TargetType')
                })
        # Get listeners
        listener_data = run_aws(f"aws elbv2 describe-listeners --load-balancer-arn {arn}")
        listeners = []
        if listener_data:
            for l in listener_data.get('Listeners', []):
                listeners.append({
                    'port': l.get('Port'),
                    'protocol': l.get('Protocol'),
                    'ssl_policy': l.get('SslPolicy')
                })
        return {
            'type': lb.get('Type'),
            'scheme': lb.get('Scheme'),
            'vpc_id': lb.get('VpcId'),
            'dns_name': lb.get('DNSName'),
            'state': lb.get('State', {}).get('Code'),
            'availability_zones': [az['ZoneName'] for az in lb.get('AvailabilityZones', [])],
            'security_groups': lb.get('SecurityGroups', []),
            'target_groups': target_groups,
            'listeners': listeners
        }
    return None

def enrich_natgateway(resource_id):
    data = run_aws(f"aws ec2 describe-nat-gateways --nat-gateway-ids {resource_id}")
    if data and data.get('NatGateways'):
        ng = data['NatGateways'][0]
        return {
            'state': ng.get('State'),
            'vpc_id': ng.get('VpcId'),
            'subnet_id': ng.get('SubnetId'),
            'connectivity_type': ng.get('ConnectivityType'),
            'public_ip': next((a.get('PublicIp') for a in ng.get('NatGatewayAddresses', [])), None),
            'private_ip': next((a.get('PrivateIp') for a in ng.get('NatGatewayAddresses', [])), None)
        }
    return None

# Load discovery data
with open(f"{PROJECT_DIR}/discovery.json") as f:
    discovery = json.load(f)

resources = discovery['resources']
total = len(resources)
enriched_count = 0
failed_count = 0

print(f"Enriching {total} resources...")
print("")

# Enrich each resource
for i, resource in enumerate(resources):
    service = resource['service']
    rtype = resource['resource_type']
    rid = resource['resource_id']
    arn = resource['arn']

    details = None

    try:
        if service == 'ec2':
            if rtype == 'instance':
                details = enrich_ec2_instance(rid)
            elif rtype == 'vpc':
                details = enrich_vpc(rid)
            elif rtype == 'subnet':
                details = enrich_subnet(rid)
            elif rtype in ('security-group', 'sg'):
                details = enrich_security_group(rid)
            elif rtype == 'natgateway':
                details = enrich_natgateway(rid)
        elif service == 'rds':
            details = enrich_rds(rid)
        elif service == 'lambda':
            details = enrich_lambda(rid)
        elif service == 'elasticloadbalancing':
            details = enrich_elb(arn)

        if details:
            resource['details'] = details
            enriched_count += 1
        else:
            resource['details'] = None
            if rtype not in ('internet-gateway', 'route-table'):
                failed_count += 1
    except Exception as e:
        resource['details'] = None
        failed_count += 1
        print(f"  WARN: Failed to enrich {arn}: {e}", file=sys.stderr)

    # Progress
    if (i + 1) % 10 == 0 or i == total - 1:
        print(f"  Progress: {i+1}/{total} ({enriched_count} enriched, {failed_count} failed)")

    # Rate limiting
    time.sleep(0.3)

# Write enriched output
discovery['resources'] = resources
discovery['metadata']['enrichment_timestamp'] = datetime.utcnow().isoformat() + 'Z'
discovery['metadata']['enriched_count'] = enriched_count
discovery['metadata']['failed_count'] = failed_count

with open(f"{PROJECT_DIR}/enriched.json", 'w') as f:
    json.dump(discovery, f, indent=2)

print("")
print(f"=== Enrichment Complete ===")
print(f"  Enriched: {enriched_count}/{total}")
print(f"  Failed: {failed_count}")
print(f"  Output: {PROJECT_DIR}/enriched.json")
PYTHON_SCRIPT
