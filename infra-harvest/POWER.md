---
name: "infra-harvest"
displayName: "Infrastructure Harvest"
description: "Discovers and maps AWS infrastructure from resource tags or ARNs. Produces an interactive system architecture diagram (HTML) and a detailed inventory summary, using official AWS component styling."
keywords: ["infrastructure", "aws", "architecture", "diagram", "inventory", "tag", "arn", "vpc", "account", "harvest", "discovery", "system diagram"]
author: "Thanachai P."
---

# Infrastructure Harvest

## Overview

This power discovers AWS infrastructure resources by querying tags or specific resource ARNs via AWS CLI. It progressively builds a complete picture of the workload — VPCs, subnets, services, connections, and cross-account relationships — then generates two HTML deliverables:

1. **Architecture Diagram** — An interactive HTML diagram using official AWS service icons showing VPCs, services, accounts, and connections.
2. **Inventory Summary** — A detailed HTML report listing every discovered resource with ARN, service type, configuration details, and relationships.

## Quick Start

### Prerequisites
- AWS CLI v2 configured with appropriate credentials/profile
- IAM permissions: `resourcegroupstaggingapi:GetResources`, `ec2:Describe*`, `ecs:Describe*`, `rds:Describe*`, `elasticloadbalancing:Describe*`, `lambda:List*`, `lambda:Get*`, etc.
- Python 3.10+ (stdlib only)
- Kiro with this power installed

### Usage

Tell Kiro what to discover:

> Harvest infrastructure for tag Environment=Production in account 123456789012, ap-southeast-1

> Harvest infrastructure for ARN arn:aws:ec2:ap-southeast-1:123456789012:vpc/vpc-0abc123

> Harvest all resources tagged Project=MyApp across us-east-1 and ap-southeast-1

Kiro will:
1. Query AWS for resources matching your tag/ARN
2. Discover related resources (VPCs, subnets, security groups, load balancers, etc.)
3. Map connections between services
4. Generate an interactive architecture diagram
5. Generate a detailed inventory summary

## Workspace Layout

```
infra-harvest/
├── infra-harvest/              ← Kiro Power (install via Powers panel)
│   ├── POWER.md                   Discovery doc + metadata
│   └── steering/
│       └── harvest-pipeline.md    Full pipeline instructions
├── .kiro/
│   └── steering/
│       └── infra-harvest-agent.md ← Minimal pointer to the power (auto-loaded)
├── scripts/
│   ├── discover_by_tag.sh         Step 1: Discover resources by tag
│   ├── discover_by_arn.sh         Step 1: Discover resources from ARN
│   ├── enrich_resources.sh        Step 2: Gather detailed info per resource
│   ├── map_connections.py         Step 3: Map relationships between resources
│   ├── generate_diagram.py        Step 4: Generate architecture diagram HTML
│   └── generate_summary.py        Step 5: Generate inventory summary HTML
├── reports/
│   └── <customer-or-project>/     ← Output goes here
│       ├── discovery.json            Raw discovery data
│       ├── enriched.json             Enriched resource details
│       ├── connections.json          Mapped connections
│       ├── architecture-diagram.html Generated diagram
│       └── inventory-summary.html    Generated summary
└── README.md
```

## Pipeline Overview

```
[User Input: Tag/ARN] → discover → enrich → map connections → generate diagram → generate summary
```

| Step | Method | Description |
|------|--------|-------------|
| 0 | Agent | Gather inputs: tag key/value OR ARN, region(s), AWS profile, project name |
| 1 | Script | Discover resources via AWS CLI (Resource Groups Tagging API or direct describe) |
| 2 | Script | Enrich each resource with detailed configuration (describe calls) |
| 3 | Script | Map connections: VPC membership, security group links, target groups, routes |
| 4 | Script+Agent | Generate interactive HTML architecture diagram with AWS icons |
| 5 | Script+Agent | Generate HTML inventory summary with all resource details |

## Supported AWS Services

The power discovers and diagrams these services:

| Category | Services |
|----------|----------|
| Compute | EC2, ECS, EKS, Lambda, Auto Scaling Groups |
| Networking | VPC, Subnets, Security Groups, NAT Gateway, Internet Gateway, Transit Gateway, Route Tables, VPC Endpoints |
| Load Balancing | ALB, NLB, CLB, Target Groups |
| Database | RDS, Aurora, DynamoDB, ElastiCache, Redshift |
| Storage | S3, EFS, EBS |
| Messaging | SQS, SNS, EventBridge |
| CDN/DNS | CloudFront, Route 53 |
| Security | WAF, Shield, KMS, Secrets Manager |
| Containers | ECR, ECS Services/Tasks, EKS Node Groups |
| Serverless | API Gateway, Step Functions, AppSync |

## Available Steering Files

- **harvest-pipeline** — Full pipeline instructions: step-by-step discovery workflow, AWS CLI commands, connection mapping logic, diagram generation, and HTML output format.

Read the pipeline steering file when harvesting infrastructure:
```
Call action "readSteering" with powerName="infra-harvest", steeringFile="harvest-pipeline.md"
```

## Diagram Design Principles

1. **Official AWS Icons** — Use AWS Architecture Icons (SVG) from the official icon set wherever possible
2. **Layered Layout** — Group by: Account → Region → VPC → Availability Zone → Subnet
3. **Connection Types** — Different line styles for: data flow, security group rules, DNS, VPC peering
4. **Interactive** — Hoverable nodes with tooltips showing key properties (ARN, type, state)
5. **Color Coding** — AWS service category colors (orange=compute, blue=network, green=database, purple=serverless)

## Best Practices

- Always verify AWS CLI credentials before running discovery scripts
- Use `--output json` for all AWS CLI calls to ensure parseable output
- Paginate results (use `--no-paginate` or handle NextToken) for large accounts
- Respect API rate limits — add small delays between describe calls if discovering many resources
- Deduplicate resources that appear in multiple queries (use ARN as unique key)
- For cross-account resources, note the account boundary clearly in the diagram
- Security groups and route tables are enriched to show actual rules/routes, not just IDs
