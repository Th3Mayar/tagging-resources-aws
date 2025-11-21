# AWS Ultimate Tag Propagator
The AWS Ultimate Tag Propagator is an automated Python-based tool designed to enforce consistent tagging standards across all EC2 resources within selected AWS regions. The script ensures that every EC2 instance, its associated EBS volumes, and related snapshots—including AMI-generated snapshots—inherit a standardized tag for billing purposes.

This tool is especially important because it allows strict cost allocation, resource tracking, and FinOps governance, ensuring that all compute-related assets can be identified and grouped programmatically.

### Purpose
The script tag_propagate.py solves a foundational AWS management problem: “EC2 instances often have Name tags, but their volumes and snapshots do not.” Without consistent tagging, cost allocation, resource cleanup, automation workflows, and compliance reporting become fragmented and unreliable.
This tool enforces tagging uniformity across every related EC2 resource—automatically and safely.

### Overview & Capabilities

This script is now the **one source of truth** for tagging compliance and full cost allocation in AWS.

| Mode                          | Resources Covered                                                                                   | Trigger Flag          |
|-------------------------------|-----------------------------------------------------------------------------------------------------|-----------------------|
| **Standard Mode** (default)   | Live EC2 instances (running/stopped) + EBS volumes + volume snapshots + AMI snapshots from live instances | No flag needed        |
| **Orphan Fix Mode**           | All orphaned AMI snapshots (even from instances terminated years ago) + source AMIs                | `--fix-orphans`       |
| **Storage Mode** (optional)   | EFS File Systems + Mount Targets + Access Points<br>All FSx types (Windows, ONTAP, OpenZFS, Lustre) including File Systems, Volumes, SVMs, Backups, File Caches | `--tag-storage`       |

The famous **empty-value key tag** (key = normalized Name, value = "") is applied everywhere → enables perfect grouping in **Cost Explorer**, **Tag Policies**, **Savings Plans**, and **Resource Groups**.

### Supported Commands

```bash
# Help
python ./scripts/tag_propagate.py --help

# Safe preview – all regions (always run first)
python ./scripts/tag_propagate.py --all-regions

# Standard tagging only (EC2 + EBS + live snapshots)
python ./scripts/tag_propagate.py --all-regions --apply

# Full tagging: EC2 + EFS + ALL FSx types
python ./scripts/tag_propagate.py --all-regions --tag-storage --apply

# One-time global cleanup of orphaned AMI snapshots
python ./scripts/tag_propagate.py --all-regions --fix-orphans --apply

# Single region examples
python ./scripts/tag_propagate.py --region us-east-1 --tag-storage --apply
python ./scripts/tag_propagate.py --region eu-west-1 --fix-orphans --apply
```

### Default Region Configuration

```python
TARGET_REGIONS = [
    "us-east-1", "us-east-2", "us-west-1", "us-west-2",
    "ap-south-1", "ap-northeast-3", "ap-northeast-2", "ap-southeast-1",
    "ap-southeast-2", "ap-northeast-1", "ca-central-1", "eu-central-1",
    "eu-west-1", "eu-west-2", "eu-west-3", "eu-north-1", "sa-east-1"
]
```

### Required IAM Permissions

```json
{
  "Effect": "Allow",
  "Action": [
    "ec2:DescribeInstances",
    "ec2:DescribeVolumes",
    "ec2:DescribeSnapshots",
    "ec2:DescribeImages",
    "ec2:DescribeRegions",
    "ec2:CreateTags",
    "elasticfilesystem:DescribeFileSystems",
    "elasticfilesystem:DescribeMountTargets",
    "elasticfilesystem:DescribeAccessPoints",
    "elasticfilesystem:CreateTags",
    "elasticfilesystem:TagResource",
    "fsx:DescribeFileSystems",
    "fsx:DescribeVolumes",
    "fsx:DescribeStorageVirtualMachines",
    "fsx:DescribeBackups",
    "fsx:TagResource"
  ],
  "Resource": "*"
}
```

### Safety & Production Features

- Dry-run by default
- 100 % idempotent – safe for daily EventBridge/Lambda execution
- Never overwrites existing tags
- Skips terminated instances
- Fully compatible with Auto Scaling Groups, CloudFormation, Launch Templates
- `--tag-storage` only adds missing tags (no impact if already compliant)
- `--fix-orphans` only touches snapshots lacking `Name` tag

### Recommended Corporate Usage

| Frequency       | Command                                                                                   |
|-----------------|-------------------------------------------------------------------------------------------|
| Daily           | `python tag_propagate.py --all-regions --tag-storage --apply`                             |
| Initial rollout | 1. Standard run<br>2. One-time: `--all-regions --fix-orphans --apply`                     |
| After large terminations | `--all-regions --fix-orphans --apply` (optional)                                          |

### Sample Output – Standard + Storage Mode

```
================================================================================
REGION: US-EAST-1 | Mode: APPLY
================================================================================
[PROCESSING] prod-web-01 (i-1234567890abcdef0) → Using tag key: 'prod-web-01'
    [APPLY] EC2 Instance i-1234567890abcdef0 → prod-web-01 = (empty)
    [APPLY] Volume vol-0abcd1234 → Name = prod-web-01

[STORAGE MODE] Processing EFS + FSx in US-EAST-1
[EFS] shared-data (fs-0a1b2c3d4e5f67890) → Using tag key: 'shared-data'
    [APPLY] EFS FileSystem fs-0a1b2c3d4e5f67890 → shared-data = (empty)

[FSx ONTAP] finance-cluster (fs-11223344556677889) → Using tag key: 'finance-cluster'
    [APPLY] FSx ONTAP FileSystem fs-11223344556677889 → finance-cluster = (empty)
    [APPLY] FSx Volume vol-0987654321 → finance-cluster = (empty)
```