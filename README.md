# AWS Ultimate Tag Propagator

The AWS Ultimate Tag Propagator is an automated Python-based tool designed to enforce consistent tagging standards across all EC2 and storage-related resources within selected AWS regions. The script ensures that every EC2 instance, its associated EBS volumes, and related snapshots—including AMI-generated snapshots—inherit a standardized tag for billing purposes.  
Optionally, it also propagates tags across EFS and all FSx types.

This tool is especially important because it allows strict cost allocation, resource tracking, and FinOps governance, ensuring that all compute- and storage-related assets can be identified and grouped programmatically.

---

### Purpose

The script `tag_propagate.py` solves a foundational AWS management problem: **“EC2 instances often have Name tags, but their volumes and snapshots do not.”**  

Without consistent tagging, cost allocation, resource cleanup, automation workflows, and compliance reporting become fragmented and unreliable.  
This tool enforces tagging uniformity across every related EC2 resource—automatically and safely.

---

### Overview & Capabilities

This script is now the **one source of truth** for tagging compliance and full cost allocation in AWS.

It supports a unified CLI entrypoint:

```bash
tagging <action> [value] [flags]
````

**Actions:**

* `all`      → process all target regions
* `set`      → process a single region
* `dry-run`  → force dry-run mode (all or one region)
* `show`     → show resources (no changes)

**Modes & Coverage**

| Mode                        | Resources Covered                                                                                                                               | How to Run (examples)                                               |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| **Standard Mode** (default) | Live EC2 instances (running/stopped) + EBS volumes + volume snapshots + AMI snapshots from live instances                                       | `tagging all` / `tagging set us-east-1`                             |
| **Orphan Fix Mode**         | All orphaned AMI snapshots (even from instances terminated years ago) + source AMIs                                                             | `tagging all --fix-orphans`                                         |
| **Storage Mode** (optional) | EFS File Systems + Access Points<br>All FSx types (Windows, ONTAP, OpenZFS, Lustre) including File Systems, Volumes, SVMs, Backups, File Caches | `tagging all --tag-storage` / `tagging set eu-west-3 --tag-storage` |

The famous **empty-value key tag** (key = normalized `Name`, value = `""`) is applied everywhere → enables perfect grouping in **Cost Explorer**, **Tag Policies**, **Savings Plans**, and **Resource Groups**.

---

### CLI Model & Default Behavior

* **Command:** `tagging`
* **DRY-RUN by default** for all actions.
* Real changes happen **only** when `--apply` is explicitly provided.
* `tagging show` and `tagging dry-run` are always non-destructive.

Examples of intent:

* “Tag all regions, dry-run only” → `tagging all`
* “Tag only `us-east-1`, dry-run” → `tagging set us-east-1`
* “Tag all regions and actually write tags” → `tagging all --apply`
* “Simulate orphan fix in a single region” → `tagging dry-run us-east-1 --fix-orphans`

---

### Supported Commands

#### Help

```bash
# Global help
tagging --help

# Help for argument errors
tagging set          # will prompt for required region
```

#### Standard Tagging (EC2 lineage: instances + EBS + snapshots)

```bash
# Safe preview – all regions (always run first)
tagging all

# Safe preview – single region
tagging set us-east-1

# Apply real changes – all regions
tagging all --apply

# Apply real changes – single region
tagging set eu-west-3 --apply
```

#### Full Tagging: EC2 + EFS + ALL FSx Types

```bash
# Dry-run across all regions
tagging all --tag-storage

# Apply real changes across all regions
tagging all --tag-storage --apply

# Single region, storage included (dry-run)
tagging set us-east-1 --tag-storage

# Single region, storage included (apply)
tagging set us-east-1 --tag-storage --apply
```

#### Orphaned AMI Snapshots Cleanup

```bash
# One-time global orphan snapshot analysis (dry-run)
tagging all --fix-orphans

# One-time global orphan snapshot cleanup (apply)
tagging all --fix-orphans --apply

# Single-region orphan snapshot dry-run
tagging dry-run us-east-1 --fix-orphans

# Single-region orphan snapshot apply
tagging set us-east-1 --fix-orphans --apply
```

#### Show Mode (Inventory / Visibility Only)

```bash
# Show counts of EC2 / EFS / FSx across all regions
tagging show

# Show counts for a specific region
tagging show eu-west-3
```

> **Note:** `show` mode is **always read-only** and never writes tags.

---

### Default Region Configuration

When `tagging all` or `tagging dry-run` (without explicit region) are used, the tool prefers this static list:

```python
TARGET_REGIONS = [
    "us-east-1", "us-east-2", "us-west-1", "us-west-2",
    "ap-south-1", "ap-northeast-3", "ap-northeast-2", "ap-southeast-1",
    "ap-southeast-2", "ap-northeast-1", "ca-central-1", "eu-central-1",
    "eu-west-1", "eu-west-2", "eu-west-3", "eu-north-1", "sa-east-1"
]
```

If this list is empty, the script falls back to `DescribeRegions()` to discover regions dynamically.

---

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

---

### Safety & Production Features

* **Dry-run by default** – no changes unless `--apply` is used.
* 100 % idempotent – safe for daily EventBridge/Lambda execution.
* Never overwrites existing tags.
* Skips terminated instances.
* Fully compatible with Auto Scaling Groups, CloudFormation, Launch Templates.
* `--tag-storage` only adds missing tags (no impact if already compliant).
* `--fix-orphans` only touches snapshots lacking a `Name` tag.
* Unified CLI actions: `all`, `set`, `dry-run`, `show` for predictable behavior.

---

### Recommended Corporate Usage

| Frequency                | Command                                        | Notes                                  |
| ------------------------ | ---------------------------------------------- | -------------------------------------- |
| Daily                    | `tagging all --tag-storage --apply`            | Keep EC2 + EFS + FSx lineage compliant |
| Initial rollout          | `tagging all` (review) → `tagging all --apply` | Validate dry-run first                 |
| One-time orphan cleanup  | `tagging all --fix-orphans --apply`            | After big cleanups / migrations        |
| After large terminations | `tagging all --fix-orphans --apply`            | Optional, to clean stale AMI snapshots |

---

### Sample Output – Standard + Storage Mode

```text
================================================================================
REGION: us-east-1 | Mode: APPLY
================================================================================
[PROCESSING] example-web-01 (i-EXAMPLEWEB01) → Using tag key: 'example-web-01'
    [APPLY] EC2 Instance i-EXAMPLEWEB01      → Name = example-web-01
    [APPLY] Volume vol-EXAMPLEWEB01-A        → Name = example-web-01
    [APPLY] Volume vol-EXAMPLEWEB01-B        → Name = example-web-01

[PROCESSING] example-api-01 (i-EXAMPLEAPI01) → Using tag key: 'example-api-01'
    [APPLY] EC2 Instance i-EXAMPLEAPI01      → Name = example-api-01
    [APPLY] Volume vol-EXAMPLEAPI01-A        → Name = example-api-01

[PROCESSING] example-worker-01 (i-EXAMPLEWRK01) → Using tag key: 'example-worker-01'
    [APPLY] EC2 Instance i-EXAMPLEWRK01      → example-worker-01 = (empty)
    [APPLY] Volume vol-EXAMPLEWRK01-A        → example-worker-01 = (empty)

[STORAGE MODE] Processing EFS + FSx in us-east-1
[EFS] example-efs-shared (fs-EXAMPLEEFS01) → Using tag key: 'example-efs-shared'
    [APPLY] EFS FileSystem fs-EXAMPLEEFS01   → example-efs-shared = (empty)

[EFS] example-efs-reports (fs-EXAMPLEEFS02) → Using tag key: 'example-efs-reports'
    [APPLY] EFS FileSystem fs-EXAMPLEEFS02   → Name = example-efs-reports

[FSx ONTAP] example-fsx-ontap (fs-EXAMPLEFSX01) → Using tag key: 'example-fsx-ontap'
    [APPLY] FSx ONTAP FileSystem fs-EXAMPLEFSX01 → example-fsx-ontap = (empty)
    [APPLY] FSx Volume fsvol-EXAMPLEFSX01-A      → example-fsx-ontap = (empty)
    [APPLY] FSx Volume fsvol-EXAMPLEFSX01-B      → example-fsx-ontap = (empty)

[FSx LUSTRE] example-fsx-lustre (fs-EXAMPLEFSX02) → Using tag key: 'example-fsx-lustre'
    [APPLY] FSx Lustre FileSystem fs-EXAMPLEFSX02 → example-fsx-lustre = (empty)


================================================================================
REGION: eu-west-3 | Mode: APPLY
================================================================================
[PROCESSING] example-web-eu-01 (i-EXAMPLEEUEC2) → Using tag key: 'example-web-eu-01'
    [APPLY] EC2 Instance i-EXAMPLEEUEC2      → Name = example-web-eu-01
    [APPLY] Volume vol-EXAMPLEEUEC2-A        → Name = example-web-eu-01

[STORAGE MODE] Processing EFS + FSx in eu-west-3
[EFS] example-efs-eu (fs-EXAMPLEEFSEU) → Using tag key: 'example-efs-eu'
    [APPLY] EFS FileSystem fs-EXAMPLEEFSEU   → example-efs-eu = (empty)

[FSx ONTAP] example-fsx-ontap-eu (fs-EXAMPLEFSXEU) → Using tag key: 'example-fsx-ontap-eu'
    [APPLY] FSx ONTAP FileSystem fs-EXAMPLEFSXEU → example-fsx-ontap-eu = (empty)
    [APPLY] FSx Volume fsvol-EXAMPLEFSXEU-A      → example-fsx-ontap-eu = (empty)
```