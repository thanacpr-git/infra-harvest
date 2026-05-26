# Infrastructure Harvest — Kiro Power

Discover, map, and visualize AWS infrastructure from resource tags or ARNs. Produces interactive HTML architecture diagrams and detailed inventory summaries.

## Quick Start

### 1. Install [Kiro IDE](https://kiro.dev)

### 2. Configure AWS CLI

```bash
aws configure  # or set AWS_PROFILE for named profiles
aws sts get-caller-identity  # verify access
```

### 3. Clone and open

```bash
git clone <this-repo>
```

Open the cloned directory as your Kiro workspace.

### 4. Install the Kiro Power

Powers panel → Add Custom Power → Local Directory → point to `infra-harvest/`

### 5. Harvest infrastructure

Tell Kiro what to discover:

> Harvest infrastructure for tag Environment=Production in account 123456789012, ap-southeast-1

> Harvest infrastructure for ARN arn:aws:ec2:ap-southeast-1:123456789012:vpc/vpc-0abc123

Kiro will:
1. Query AWS for matching resources
2. Discover related resources (VPCs, subnets, security groups, etc.)
3. Enrich each resource with detailed configuration
4. Map connections between services
5. Generate an interactive architecture diagram (`architecture-diagram.html`)
6. Generate a detailed inventory summary (`inventory-summary.html`)

## What's in this repo

```
├── infra-harvest/              ← Kiro Power (install via Powers panel)
│   ├── POWER.md                   Discovery doc + metadata
│   └── steering/
│       └── harvest-pipeline.md    Full pipeline instructions
├── .kiro/
│   └── steering/
│       └── infra-harvest-agent.md ← Minimal pointer (auto-loaded)
├── scripts/
│   ├── discover_by_tag.sh         Discover resources by tag
│   ├── discover_by_arn.sh         Discover resources from ARN
│   ├── enrich_resources.sh        Gather detailed configs
│   ├── map_connections.py         Map relationships
│   ├── generate_diagram.py        Generate architecture diagram HTML
│   └── generate_summary.py        Generate inventory summary HTML
├── reports/                    ← Your reports go here (gitignored)
└── README.md
```

## Pipeline

```
[User Input] → discover → enrich → map connections → generate diagram → generate summary
```

| Step | Script | Description |
|------|--------|-------------|
| 1a | `discover_by_tag.sh` | Find resources by tag key/value via Resource Groups Tagging API |
| 1b | `discover_by_arn.sh` | Start from a known ARN, discover related resources |
| 2 | `enrich_resources.sh` | Run describe calls per resource for detailed config |
| 3 | `map_connections.py` | Analyze security groups, load balancers, routes, VPC membership |
| 4 | `generate_diagram.py` | Produce interactive HTML architecture diagram |
| 5 | `generate_summary.py` | Produce HTML inventory with sortable tables, CSV export |

## Requirements

- [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured with appropriate profile
- Python 3.10+ (stdlib only, no external dependencies)
- IAM permissions:
  - `resourcegroupstaggingapi:GetResources`
  - `ec2:Describe*`
  - `ecs:Describe*`, `ecs:List*`
  - `rds:Describe*`
  - `elasticloadbalancing:Describe*`
  - `lambda:List*`, `lambda:GetFunction`
  - `s3:GetBucketLocation`, `s3:GetBucketTagging`
  - `dynamodb:DescribeTable`
  - `sqs:GetQueueAttributes`
  - `sts:GetCallerIdentity`

## Manual Usage (without Kiro)

```bash
# Discovery
./scripts/discover_by_tag.sh "Environment" "Production" "ap-southeast-1" "default" "reports/my-project"

# Enrichment
./scripts/enrich_resources.sh "reports/my-project" "ap-southeast-1" "default"

# Map connections
python3 scripts/map_connections.py "reports/my-project"

# Generate outputs
python3 scripts/generate_diagram.py "reports/my-project"
python3 scripts/generate_summary.py "reports/my-project"

# Open results
open reports/my-project/architecture-diagram.html
open reports/my-project/inventory-summary.html
```

## Output Examples

### Architecture Diagram
- Layered layout: Account → Region → VPC → AZ → Subnet
- AWS service color coding
- Interactive hover tooltips with ARN and key config
- Click to highlight connected resources
- Print-friendly

### Inventory Summary
- Executive overview with resource counts
- Sortable, filterable resource table
- Click-to-copy ARNs
- CSV export button
- Service breakdown chart
- Connection type summary

## Supported Services

Compute, Networking, Load Balancing, Database, Storage, Messaging, CDN/DNS, Security, Containers, Serverless — see POWER.md for the full list.
