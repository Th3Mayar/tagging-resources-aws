#!/usr/bin/env python3
"""
AWS Ultimate Tag Propagator – Name + Empty Key Tag
Now with optional --tag-storage to cover EFS + ALL FSx types
"""

import argparse
import sys
import re
from typing import List

import boto3
from botocore.exceptions import ClientError


TARGET_REGIONS = [
    "us-east-1",
    "us-east-2",
    "us-west-1",
    "us-west-2",
    "ap-south-1",
    "ap-northeast-3",
    "ap-northeast-2",
    "ap-southeast-1",
    "ap-southeast-2",
    "ap-northeast-1",
    "ca-central-1",
    "eu-central-1",
    "eu-west-1",
    "eu-west-2",
    "eu-west-3",
    "eu-north-1",
    "sa-east-1"
]

class ListHelpAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        print(
            "usage: tagging [OPTIONS] {all,set,dry-run,show} [value]\n"
        )
        print("Description:")
        print("  Ultimate Tag Propagator – EC2 + EFS + ALL FSx types in a single command!\n")

        print("Modes (positional arguments):")
        print("  all       Process all supported regions in DRY-RUN or APPLY mode.")
        print("  set       Process a single region only. Example: tagging set us-east-1 --apply")
        print("  dry-run   Force DRY-RUN mode (all or one region). Never applies changes.")
        print("  show      Show resources only (no tagging, no lineage, no changes).\n")

        print("Value (optional positional):")
        print("  For 'set'      Region name, e.g. us-east-1")
        print("  For 'dry-run'  Optional region (default: all regions)")
        print("  For 'show'     Optional region (default: all regions)\n")

        print("Options:")
        print("  -h, --help, --h   Show this help message and exit.")
        print("  --apply           Apply real changes. If not set, everything runs in DRY-RUN mode.")
        print("  --fix-orphans     ONLY fix orphaned AMI snapshots (no EC2/Storage lineage tagging).")
        print("  --tag-storage     Also tag EFS + all FSx types (EFS, FSx ONTAP, FSx Lustre, etc.).\n")

        parser.exit(0)

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tagging",
        description="Ultimate Tag Propagator – EC2 + EFS + ALL FSx types in a single command!",
        add_help=False, 
    )

    # Help custom: -h, --help y --h
    parser.add_argument(
        "-h",
        "--help",
        "--h",
        action=ListHelpAction,
        nargs=0,
        help="Show this help message and exit.",
    )

    parser.add_argument(
        "action",
        choices=["all", "set", "dry-run", "show"],
        help="Operation mode (see --help for details).",
    )

    parser.add_argument(
        "value",
        nargs="?",
        help="Optional value depending on the selected mode.",
    )

    # flags
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply real changes. If not set, everything runs in DRY-RUN mode.",
    )

    parser.add_argument(
        "--fix-orphans",
        action="store_true",
        help="ONLY fix orphaned AMI snapshots (no EC2/Storage lineage tagging).",
    )

    parser.add_argument(
        "--tag-storage",
        action="store_true",
        help="Also tag EFS + all FSx types in each region.",
    )

    return parser


# =============================================================================
# ============================== EC2 CODE =====================================
# =============================================================================

def get_machine_key(instance) -> str:
    if instance.tags:
        for tag in instance.tags:
            if tag.get("Key") == "Name" and tag.get("Value"):
                name = " ".join(tag["Value"].strip().split())
                return name.replace(" ", "-")
    return instance.id


def list_all_regions() -> List[str]:
    """
    Return the list of regions to use when the user asks for 'all'.
    Prefer TARGET_REGIONS, otherwise fall back to DescribeRegions().
    """
    if TARGET_REGIONS:
        return TARGET_REGIONS

    ec2 = boto3.client("ec2")
    return [r["RegionName"] for r in ec2.describe_regions()["Regions"]]


def show_region(region: str) -> None:
    """
    Light 'show' mode: list how many EC2 instances, EFS and FSx
    resources exist in the region. This does not modify anything.
    """
    print(f"\n{'=' * 80}")
    print(f"[SHOW] REGION: {region.upper()}")
    print(f"{'=' * 80}")

    # EC2 instances
    ec2 = boto3.resource("ec2", region_name=region)
    instances = list(ec2.instances.all())
    print(f"[EC2] Instances: {len(instances)}")

    # EFS
    try:
        efs = boto3.client("efs", region_name=region)
        file_systems = efs.describe_file_systems().get("FileSystems", [])
        print(f"[EFS] FileSystems: {len(file_systems)}")
    except Exception:
        print("[EFS] Not accessible or no EFS in this region")

    # FSx
    try:
        fsx = boto3.client("fsx", region_name=region)
        fss = fsx.describe_file_systems().get("FileSystems", [])
        print(f"[FSx] FileSystems: {len(fss)}")
    except Exception:
        print("[FSx] Not accessible or no FSx in this region")


def plan_or_apply(client, resource_id: str, tags_to_add: List[dict], resource_type: str, dry_run: bool):
    if not tags_to_add:
        return

    if dry_run:
        for t in tags_to_add:
            value = t["Value"] if t["Value"] else "(empty)"
            print(f"    [PLAN] {resource_type} {resource_id} → {t['Key']} = {value}")
        return

    try:
        client.create_tags(Resources=[resource_id], Tags=tags_to_add)
        for t in tags_to_add:
            value = t["Value"] if t["Value"] else "(empty)"
            print(f"    [APPLY] {resource_type} {resource_id} → {t['Key']} = {value}")
    except ClientError as e:
        print(f"    [ERROR] {resource_type} {resource_id}: {e}", file=sys.stderr)


def process_resource(ec2_client, resource_id: str, machine_key: str, name_value: str, resource_type: str, dry_run: bool):
    try:
        if resource_type == "Volume":
            data = ec2_client.describe_volumes(VolumeIds=[resource_id])["Volumes"][0]
        else:  # Snapshot
            data = ec2_client.describe_snapshots(SnapshotIds=[resource_id])["Snapshots"][0]

        current = {t["Key"]: t["Value"] for t in data.get("Tags", [])}
        tags_to_add = []

        if "Name" not in current:
            tags_to_add.append({"Key": "Name", "Value": name_value})
        if machine_key not in current:
            tags_to_add.append({"Key": machine_key, "Value": ""})

        plan_or_apply(ec2_client, resource_id, tags_to_add, resource_type, dry_run)

    except ClientError as e:
        print(f"    [ERROR] {resource_type} {resource_id}: {e}", file=sys.stderr)


def tag_volumes_and_snapshots(ec2_client, instance, machine_key: str, name_value: str, dry_run: bool):
    volume_ids = []
    for mapping in instance.block_device_mappings:
        vol_id = mapping.get("Ebs", {}).get("VolumeId")
        if not vol_id:
            continue
        volume_ids.append(vol_id)
        process_resource(ec2_client, vol_id, machine_key, name_value, "Volume", dry_run)

    # Snapshots from volumes
    if volume_ids:
        paginator = ec2_client.get_paginator('describe_snapshots')
        for page in paginator.paginate(OwnerIds=['self'], Filters=[{'Name': 'volume-id', 'Values': volume_ids}]):
            for snap in page["Snapshots"]:
                process_resource(ec2_client, snap["SnapshotId"], machine_key, name_value, "Snapshot", dry_run)

    # AMI / CreateImage snapshots (by instance-id in description)
    paginator = ec2_client.get_paginator('describe_snapshots')
    for page in paginator.paginate(OwnerIds=['self'], Filters=[{'Name': 'description', 'Values': [f'*{instance.id}*']}]):
        for snap in page["Snapshots"]:
            if instance.id not in (snap.get("Description") or ""):
                continue
            process_resource(ec2_client, snap["SnapshotId"], machine_key, name_value, "Snapshot (AMI)", dry_run)


def process_instance(ec2_client, instance, dry_run: bool):
    instance.load()
    if instance.state["Name"] == "terminated":
        return

    machine_key = get_machine_key(instance)
    name_value = next((t["Value"] for t in (instance.tags or []) if t["Key"] == "Name"), None) or instance.id
    display = f"{name_value} ({instance.id})" if name_value != instance.id else instance.id

    print(f"\n[PROCESSING] {display} → Using tag key: '{machine_key}'")

    # Instance itself
    current = {t["Key"]: t["Value"] for t in (instance.tags or [])}
    tags_to_add = []
    if "Name" not in current:
        tags_to_add.append({"Key": "Name", "Value": name_value})
    if machine_key not in current:
        tags_to_add.append({"Key": machine_key, "Value": ""})
    plan_or_apply(ec2_client, instance.id, tags_to_add, "EC2 Instance", dry_run)

    # Volumes + Snapshots
    tag_volumes_and_snapshots(ec2_client, instance, machine_key, name_value, dry_run)


def process_region(region: str, dry_run: bool):
    print(f"\n{'=' * 80}")
    print(f"REGION: {region.upper()} | Mode: {'DRY-RUN' if dry_run else 'APPLY'}")
    print(f"{'=' * 80}")

    ec2_client = boto3.client('ec2', region_name=region)
    resource = boto3.resource('ec2', region_name=region)

    count = 0
    for instance in resource.instances.filter(Filters=[{'Name': 'instance-state-name', 'Values': ['running', 'stopped']}]):
        process_instance(ec2_client, instance, dry_run)
        count += 1

    print(f"[SUMMARY] {region} → {count} instances processed")


def get_regions(args):
    if args.region:
        return [args.region]
    if args.all_regions:
        ec2 = boto3.client('ec2')
        return [r['RegionName'] for r in ec2.describe_regions()['Regions']]
    if TARGET_REGIONS:
        return TARGET_REGIONS
    ec2 = boto3.client('ec2')
    return [r['RegionName'] for r in ec2.describe_regions()['Regions']]


def fix_orphaned_ami_snapshots(ec2_client, dry_run: bool):
    print("\n[ORPHAN MODE] Fixing orphaned AMI snapshots that have no Name tag...")
    paginator = ec2_client.get_paginator('describe_snapshots')
    fixed = 0

    for page in paginator.paginate(OwnerIds=['self']):
        for snap in page["Snapshots"]:
            snap_id = snap["SnapshotId"]
            desc = snap.get("Description", "").lower()

            if "ami-" not in desc:
                continue

            ami_ids = re.findall(r"(ami-[0-9a-f]{8,17})", desc)
            if not ami_ids:
                continue

            current_tags = {t["Key"]: t["Value"] for t in snap.get("Tags", [])}
            if "Name" in current_tags:
                continue

            ami_name = None
            ami_key = None
            for ami_id in ami_ids:
                try:
                    img = ec2_client.describe_images(ImageIds=[ami_id])["Images"][0]
                    ami_name = next((t["Value"] for t in img.get("Tags", []) if t["Key"] == "Name"), None)
                    if not ami_name:
                        ami_name = img.get("Name") or ami_id
                    ami_key = re.sub(r"[^a-zA-Z0-9\-]", "-", ami_name)
                    break
                except:
                    continue

            if not ami_name:
                continue

            print(f"\n[ORPHAN FIXED] Snapshot {snap_id} → Using AMI name: '{ami_name}'")
            to_add = [{"Key": "Name", "Value": ami_name}]
            if ami_key not in current_tags:
                to_add.append({"Key": ami_key, "Value": ""})
            plan_or_apply(ec2_client, snap_id, to_add, "Snapshot (Orphan-AMI)", dry_run)

            try:
                img = ec2_client.describe_images(ImageIds=[ami_id])["Images"][0]
                ami_tags = {t["Key"]: t["Value"] for t in img.get("Tags", [])}
                if ami_key and ami_key not in ami_tags:
                    plan_or_apply(ec2_client, ami_id, [{"Key": ami_key, "Value": ""}], "Image", dry_run)
            except:
                pass

            fixed += 1

    print(f"\n[ORPHAN MODE] Completed → {fixed} orphaned AMI snapshots fixed!")


# =============================================================================
# ============================== EFS + FSx CODE ===============================
# =============================================================================


def normalize_storage_key(name: str) -> str:
    """
    Normalize a storage-related tag key (EFS/FSx) so it is tag-safe:
      - strip
      - replace non-alphanumeric/- with '-'
      - replace spaces with '-'
    """
    name = name.strip()
    name = re.sub(r"[^a-zA-Z0-9\-\s]", "-", name)
    return name.replace(" ", "-")


def plan_or_apply_storage(
    client,
    resource_id_or_arn: str,
    tags_to_add: List[dict],
    resource_type: str,
    dry_run: bool,
) -> None:
    """
    Generic tagging helper for EFS + FSx.

    For EFS:
      - Uses TagResource(ResourceId=fs-.../fsap-...)
    For FSx:
      - Uses TagResource(ResourceARN=arn:aws:fsx:...)
    """
    if not tags_to_add:
        return

    action = "PLAN" if dry_run else "APPLY"
    short_id = resource_id_or_arn.split("/")[-1] if "/" in resource_id_or_arn else resource_id_or_arn
    for t in tags_to_add:
        val = t["Value"] if t["Value"] else "(empty)"
        print(f"    [{action}] {resource_type} {short_id} → {t['Key']} = {val}")

    if dry_run:
        return

    try:
        service = client.meta.service_model.service_name

        if service == "efs":
            # EFS tagging: TagResource(ResourceId=fs-.../fsap-...)
            client.tag_resource(ResourceId=resource_id_or_arn, Tags=tags_to_add)
        else:
            # FSx tagging: TagResource(ResourceARN=arn:aws:fsx:...)
            client.tag_resource(ResourceARN=resource_id_or_arn, Tags=tags_to_add)

    except ClientError as e:
        print(f"    [ERROR] {resource_type} {short_id}: {e}", file=sys.stderr)


def get_current_tags_storage(client, resource_id_or_arn: str) -> dict:
    """
    Fetch current tags for EFS / FSx using the appropriate ListTagsForResource call.
    """
    try:
        service = client.meta.service_model.service_name

        if service == "efs":
            # EFS: ListTagsForResource(ResourceId=fs-... or fsap-...)
            resp = client.list_tags_for_resource(ResourceId=resource_id_or_arn)
            return {t["Key"]: t["Value"] for t in resp.get("Tags", [])}

        # FSx: ListTagsForResource(ResourceARN=arn:aws:fsx:...)
        if resource_id_or_arn.startswith("arn:"):
            resp = client.list_tags_for_resource(ResourceARN=resource_id_or_arn)
            return {t["Key"]: t["Value"] for t in resp.get("Tags", [])}

        return {}
    except Exception:
        return {}


def process_efs_and_fsx(region: str, dry_run: bool) -> None:
    """
    Tag EFS FileSystems + AccessPoints and all FSx types (FileSystems, Backups,
    Volumes, SVMs) in the given region.
    """
    print(f"\n[STORAGE MODE] Processing EFS + FSx in {region.upper()}")

    # === EFS ===
    try:
        efs = boto3.client("efs", region_name=region)

        response = efs.describe_file_systems()
        file_systems = response.get("FileSystems", [])

        if not file_systems:
            print(f"[EFS] No EFS file systems found in {region.upper()}")
        else:
            for fs in file_systems:
                fs_id = fs["FileSystemId"]
                name_tag = next(
                    (t["Value"] for t in fs.get("Tags", []) if t["Key"].lower() == "name"),
                    None,
                )
                name = name_tag or fs_id
                key = normalize_storage_key(name)

                print(f"\n[EFS] {name} ({fs_id}) → Using tag key: '{key}'")

                # FileSystem – tag by FileSystemId (ResourceId)
                current = get_current_tags_storage(efs, fs_id)
                to_add: List[dict] = []
                if "Name" not in current:
                    to_add.append({"Key": "Name", "Value": name})
                if key not in current:
                    to_add.append({"Key": key, "Value": ""})
                plan_or_apply_storage(efs, fs_id, to_add, "EFS FileSystem", dry_run)

                # Access Points – tag by AccessPointId (fsap-...)
                try:
                    aps = efs.describe_access_points(FileSystemId=fs_id).get("AccessPoints", [])
                    for ap in aps:
                        ap_id = ap["AccessPointId"]  # fsap-xxxx
                        current_ap = get_current_tags_storage(efs, ap_id)
                        if key in current_ap:
                            continue
                        plan_or_apply_storage(
                            efs,
                            ap_id,
                            [{"Key": key, "Value": ""}],
                            "EFS AccessPoint",
                            dry_run,
                        )
                except ClientError as e:
                    print(f"    [WARN] Access Points error: {e}")

                # NOTE: Mount Targets are not taggable via EFS tagging APIs.
                # We intentionally skip them to avoid bogus API calls.

    except ClientError as e:
        if "AccessDenied" in str(e):
            print(
                f"[EFS] Access denied in {region.upper()} – "
                f"ensure elasticfilesystem:DescribeFileSystems/ListTagsForResource/TagResource are allowed."
            )
        else:
            print(f"[EFS] AWS error in {region.upper()}: {e}")
    except Exception as e:
        print(f"[EFS] Unexpected error in {region.upper()}: {e}")

    # === FSx ===
    try:
        fsx = boto3.client("fsx", region_name=region)
        file_systems = fsx.describe_file_systems().get("FileSystems", [])

        if not file_systems:
            print(f"[FSx] No FSx file systems found in {region.upper()}")
            return

        for fs in file_systems:
            fs_id = fs["FileSystemId"]
            fs_type = fs["FileSystemType"]
            arn = fs["ResourceARN"]
            name_tag = next(
                (t["Value"] for t in fs.get("Tags", []) if t["Key"].lower() == "name"),
                None,
            )
            name = name_tag or fs_id
            key = normalize_storage_key(name)

            print(f"\n[FSx {fs_type}] {name} ({fs_id}) → Using tag key: '{key}'")

            # FileSystem
            current = get_current_tags_storage(fsx, arn)
            to_add_fs: List[dict] = []
            if "Name" not in current:
                to_add_fs.append({"Key": "Name", "Value": name})
            if key not in current:
                to_add_fs.append({"Key": key, "Value": ""})
            plan_or_apply_storage(fsx, arn, to_add_fs, f"FSx {fs_type} FileSystem", dry_run)

            # Backups
            backups = fsx.describe_backups(
                Filters=[{"Name": "file-system-id", "Values": [fs_id]}]
            ).get("Backups", [])
            for backup in backups:
                b_arn = backup["ResourceARN"]
                current_b = get_current_tags_storage(fsx, b_arn)
                if key not in current_b:
                    plan_or_apply_storage(
                        fsx,
                        b_arn,
                        [{"Key": key, "Value": ""}],
                        "FSx Backup",
                        dry_run,
                    )

            # Volumes (for ONTAP, WINDOWS, OPENZFS)
            if fs_type in ("ONTAP", "WINDOWS", "OPENZFS"):
                volumes = fsx.describe_volumes(
                    Filters=[{"Name": "file-system-id", "Values": [fs_id]}]
                ).get("Volumes", [])
                for vol in volumes:
                    v_arn = vol["ResourceARN"]
                    current_v = get_current_tags_storage(fsx, v_arn)
                    if key not in current_v:
                        plan_or_apply_storage(
                            fsx,
                            v_arn,
                            [{"Key": key, "Value": ""}],
                            "FSx Volume",
                            dry_run,
                        )

            # Storage Virtual Machines (ONTAP only)
            if fs_type == "ONTAP":
                svms = fsx.describe_storage_virtual_machines(
                    Filters=[{"Name": "file-system-id", "Values": [fs_id]}]
                ).get("StorageVirtualMachines", [])
                for svm in svms:
                    svm_arn = svm["ResourceARN"]
                    current_s = get_current_tags_storage(fsx, svm_arn)
                    if key not in current_s:
                        plan_or_apply_storage(
                            fsx,
                            svm_arn,
                            [{"Key": key, "Value": ""}],
                            "FSx SVM",
                            dry_run,
                        )

    except ClientError as e:
        if "AccessDenied" in str(e):
            print(
                f"[FSx] Access denied or limited permissions in {region.upper()} – "
                f"ensure fsx:Describe*/ListTagsForResource/TagResource are allowed."
            )
        else:
            print(f"[FSx] AWS error in {region.upper()}: {e}")
    except Exception as e:
        print(f"[FSx] No FSx or permission issue in {region.upper()}: {e}")


# =============================================================================
# ============================== MAIN CODE ====================================
# =============================================================================
def main() -> None:
    """
    CLI entrypoint for the `tagging` command.

    Default behavior:
    - ALWAYS dry-run by default.
    - Only applies real changes when --apply is used.

    Supported commands:
      tagging all [--apply] [--tag-storage] [--fix-orphans]
      tagging set <region> [--apply] [--tag-storage] [--fix-orphans]
      tagging dry-run [<region>] [--tag-storage] [--fix-orphans]
      tagging show [<region>]
    """
    parser = build_parser()
    args = parser.parse_args()

    action = args.action
    value = args.value

    # --------------------------------------------------
    # Resolve DRY-RUN behavior
    # --------------------------------------------------
    if action == "dry-run":
        # For 'dry-run' action we always force dry-run,
        # ignoring --apply if someone lo pone por error.
        dry_run = True
    elif action == "show":
        # 'show' nunca modifica nada.
        dry_run = True
    else:
        # Default: DRY-RUN a menos que el user ponga --apply
        dry_run = not args.apply

    # --------------------------------------------------
    # Resolve regions based on action/value
    # --------------------------------------------------
    if action == "all":
        # tagging all [--apply]
        regions = list_all_regions()

    elif action == "dry-run":
        # tagging dry-run            → all regions
        # tagging dry-run us-east-1  → single region
        if value is None:
            regions = list_all_regions()
        else:
            regions = [value]

    elif action in ("set", "show"):
        # tagging set us-east-1
        # tagging show us-east-1 / tagging show
        if action == "set" and value is None:
            parser.error("Region is required for 'set' action. Example: tagging set us-east-1")

        if value is None:
            regions = list_all_regions()
        else:
            regions = [value]

    else:
        parser.error(f"Unknown action: {action}")

    # --------------------------------------------------
    # SHOW MODE (read-only)
    # --------------------------------------------------
    if action == "show":
        print("\n[SHOW MODE] No changes will be made.")
        for region in sorted(regions):
            show_region(region)
        return

    # --------------------------------------------------
    # ORPHAN-ONLY MODE
    # --------------------------------------------------
    if args.fix_orphans:
        print(
            f"\n=== ORPHANED AMI SNAPSHOT FIX MODE "
            f"{'(DRY-RUN)' if dry_run else '(APPLY)'} ==="
        )
        print(f"Target regions: {', '.join(sorted(regions))}\n")

        for region in sorted(regions):
            print(f"{'=' * 80}")
            print(f"REGION: {region.upper()} | Orphan Fix Mode")
            print(f"{'=' * 80}")
            ec2_client = boto3.client("ec2", region_name=region)
            fix_orphaned_ami_snapshots(ec2_client, dry_run)
        return

    # --------------------------------------------------
    # Normal EC2 + optional storage mode
    # --------------------------------------------------
    print(f"\n{'DRY-RUN MODE' if dry_run else 'APPLY MODE – REAL CHANGES!'}")
    print(f"Action: {action}")
    print(f"Target regions: {', '.join(sorted(regions))}\n")

    for region in sorted(regions):
        process_region(region, dry_run)

        if args.tag_storage:
            process_efs_and_fsx(region, dry_run)

    print("\n" + "═" * 80)
    print("TAG PROPAGATION COMPLETED!")
    if args.tag_storage:
        print("→ EC2 + EFS + ALL FSx types processed (check logs for any WARN/ERROR).")
    else:
        print("→ EC2 lineage tagging only (instances + EBS + snapshots).")
    print("═" * 80)


if __name__ == "__main__":
    main()