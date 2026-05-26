---
inclusion: auto
description: "Pointer to the infra-harvest power for infrastructure discovery and diagramming."
---

# Infrastructure Harvest

This workspace uses the **infra-harvest** power to discover and visualize AWS infrastructure.

## When to Activate

Activate when the user asks to:
- Discover/harvest infrastructure from an AWS account
- Map resources by tag or ARN
- Generate an architecture diagram
- Create an inventory of AWS resources
- Visualize a workload's architecture

## How to Use

Load the full pipeline instructions:
```
Call action "readSteering" with powerName="infra-harvest", steeringFile="harvest-pipeline.md"
```

Then follow the pipeline steps sequentially.
