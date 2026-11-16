"""Import only resources from the 2026-11-16 interrupted creation.

No Terraform apply, resource deletion, forced state overwrite or -lock=false occurs.
An explicitly identified stale lock can be released after failed-run checks.
State backups stay in the protected S3 backend bucket, never public artifacts.
"""
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

BUCKET = "sentinel-tfstate-485378272094-eu-north-1"
KEY = "sentinel/terraform.tfstate"
ACCOUNT = "485378272094"
VPCS = {"gateway": "vpc-00127c0d370f4e9b2", "backend": "vpc-08829c8d48837184a"}
NATS = {"gateway": "nat-0ac478601d695daeb", "backend": "nat-0fc353373210cdebe"}
SG = "sg-0dc8d607af1fc0ec4"
RULE = "sgr-0ee4ba5dda241838b"
INSTANCE = "i-0138e5cfebfd91401"


def run(*args):
    result = subprocess.run(args, text=True, capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError(f"{args[0]} command failed: {result.stderr.strip()}")
    return result.stdout


def aws(service, operation, *args):
    return json.loads(run("aws", service, operation, *args, "--region", "eu-north-1",
                          "--output", "json", "--no-cli-pager") or "{}")


def remaining_seconds(expiration, now=None):
    expiry = dt.datetime.fromisoformat(expiration.replace("Z", "+00:00"))
    if expiry.tzinfo is None:
        raise ValueError("Credential expiration must include a timezone")
    return (expiry - (now or dt.datetime.now(dt.timezone.utc))).total_seconds()


def require_time(minimum):
    if remaining_seconds(os.environ["CREDENTIAL_EXPIRATION"]) < minimum:
        raise RuntimeError("Insufficient credential lifetime; refresh all bootstrap secrets and expiration before recovery")


def state_instances(state):
    result = {}
    for resource in state.get("resources", []):
        if resource.get("mode") != "managed":
            continue
        base = ".".join(filter(None, [resource.get("module"), resource["type"], resource["name"]]))
        for instance in resource.get("instances", []):
            key = instance.get("index_key")
            address = base if key is None else f"{base}[{json.dumps(key)}]"
            if address in result:
                raise RuntimeError("Duplicate/deposed state instances require manual review")
            result[address] = instance.get("attributes", {})
    return result


def candidates(instances):
    imports = [
        ('module.eks["gateway"].aws_eks_cluster.this', "eks-gateway", {"name": "eks-gateway"}),
        ('module.eks["backend"].aws_eks_cluster.this', "eks-backend", {"name": "eks-backend"}),
        ('module.network["gateway"].aws_nat_gateway.this', NATS["gateway"], {"id": NATS["gateway"]}),
        ("module.runner.aws_security_group.runner", SG, {"id": SG}),
        ("module.runner.aws_vpc_security_group_egress_rule.https", RULE, {"id": RULE}),
        ("module.runner.aws_instance.runner", INSTANCE, {"id": INSTANCE}),
    ]
    for domain in VPCS:
        for az in ("a", "b"):
            rt = instances[f'module.network["{domain}"].aws_route_table.private["{az}"]']["id"]
            address = f'module.network["{domain}"].aws_route.private_internet["{az}"]'
            imports.append((address, rt + "_0.0.0.0/0", {
                "route_table_id": rt, "destination_cidr_block": "0.0.0.0/0", "nat_gateway_id": NATS[domain],
            }))
    return imports


def missing_imports(instances):
    missing = []
    for address, identifier, expected in candidates(instances):
        if address in instances:
            if any(instances[address].get(k) != v for k, v in expected.items()):
                raise RuntimeError(f"State mapping differs from incident inventory: {address}")
        else:
            missing.append((address, identifier))
    return missing


def verify_failed_run():
    run_id = os.environ["FAILED_RUN_ID"]
    if not run_id.isdigit():
        raise ValueError("Failed run ID must be numeric")
    url = f'{os.environ["GITHUB_API_URL"]}/repos/{os.environ["GITHUB_REPOSITORY"]}/actions/runs/{run_id}'
    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + os.environ["GH_TOKEN"], "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        record = json.load(response)
    if (record["status"] != "completed" or record["conclusion"] not in ("failure", "cancelled", "timed_out")
            or record["path"].split("@")[0] != ".github/workflows/terraform-plan.yml"
            or record["head_branch"] != "main"):
        raise RuntimeError("The supplied run must be a completed failed Terraform deploy on main")


def verify_inventory(instances):
    for domain, vpc in VPCS.items():
        tracked = instances[f'module.network["{domain}"].aws_vpc.this']["id"]
        cluster = aws("eks", "describe-cluster", "--name", "eks-" + domain)["cluster"]
        if tracked != vpc or cluster["resourcesVpcConfig"]["vpcId"] != vpc or cluster["status"] != "ACTIVE":
            raise RuntimeError("Cluster/VPC mismatch or cluster not ACTIVE")
        nat = aws("ec2", "describe-nat-gateways", "--nat-gateway-ids", NATS[domain])["NatGateways"]
        if len(nat) != 1 or nat[0]["VpcId"] != vpc or nat[0]["State"] != "available":
            raise RuntimeError("NAT gateway inventory mismatch")
        for az in ("a", "b"):
            rt = instances[f'module.network["{domain}"].aws_route_table.private["{az}"]']["id"]
            tables = aws("ec2", "describe-route-tables", "--route-table-ids", rt)["RouteTables"]
            if len(tables) != 1 or tables[0]["VpcId"] != vpc:
                raise RuntimeError("Route table inventory mismatch")
            routes = [r for r in tables[0]["Routes"] if r.get("DestinationCidrBlock") == "0.0.0.0/0"]
            if len(routes) != 1 or routes[0].get("NatGatewayId") != NATS[domain] or routes[0]["State"] != "active":
                raise RuntimeError("Expected private NAT route is missing or different")
    group = aws("ec2", "describe-security-groups", "--group-ids", SG)["SecurityGroups"][0]
    if group["VpcId"] != VPCS["gateway"] or not group["GroupName"].startswith("sentinel-private-runner-"):
        raise RuntimeError("Runner security group mismatch")
    rules = aws("ec2", "describe-security-group-rules", "--security-group-rule-ids", RULE)["SecurityGroupRules"]
    if len(rules) != 1 or any(rules[0].get(k) != v for k, v in {
        "GroupId": SG, "IsEgress": True, "IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "CidrIpv4": "0.0.0.0/0",
    }.items()):
        raise RuntimeError("Runner HTTPS rule mismatch")
    runner = aws("ec2", "describe-instances", "--instance-ids", INSTANCE)["Reservations"][0]["Instances"][0]
    if (runner["VpcId"] != VPCS["gateway"] or runner["SubnetId"] != instances[
            'module.network["gateway"].aws_subnet.private["a"]']["id"]
            or {g["GroupId"] for g in runner["SecurityGroups"]} != {SG}
            or runner["State"]["Name"] != "running"):
        raise RuntimeError("Runner instance inventory mismatch")


def main():
    if os.environ.get("CONFIRMATION") != "RECOVER-SENTINEL":
        raise RuntimeError("Recovery confirmation is missing")
    require_time(600)
    if aws("sts", "get-caller-identity")["Account"] != ACCOUNT:
        raise RuntimeError("Wrong AWS account")
    verify_failed_run()
    state = json.loads(run("terraform", "state", "pull"))
    instances = state_instances(state)
    verify_inventory(instances)
    imports = missing_imports(instances)
    print(f"Inventory verified. Missing state bindings: {len(imports)}", flush=True)
    for address, _ in imports:
        print(address, flush=True)
    # Backup before any unlock or import. Files never enter a public artifact.
    backup = Path(os.environ["RUNNER_TEMP"]) / "sentinel-before-recovery.tfstate"
    backup.write_text(json.dumps(state))
    os.chmod(backup, 0o600)
    backup_key = f'sentinel/recovery/{os.environ["GITHUB_RUN_ID"]}/{os.environ["GITHUB_RUN_ATTEMPT"]}/before.tfstate'
    aws("s3api", "put-object", "--bucket", BUCKET, "--key", backup_key,
        "--body", str(backup), "--server-side-encryption", "AES256")
    print("Protected S3 state backup saved: " + backup_key, flush=True)
    lock_result = aws("s3api", "list-objects-v2", "--bucket", BUCKET, "--prefix", KEY + ".tflock")
    lock_exists = any(item["Key"] == KEY + ".tflock" for item in lock_result.get("Contents", []))
    if lock_exists:
        lock_file = Path(os.environ["RUNNER_TEMP"]) / "sentinel-stale-lock.json"
        aws("s3api", "get-object", "--bucket", BUCKET, "--key", KEY + ".tflock", str(lock_file))
        lock = json.loads(lock_file.read_text())
        if not os.environ.get("STALE_LOCK_ID") or lock["ID"] != os.environ["STALE_LOCK_ID"]:
            raise RuntimeError("Lock exists: provide its reviewed ID after confirming no active Terraform operation")
        require_time(480)
        print(run("terraform", "force-unlock", "-force", lock["ID"]), flush=True)
    elif os.environ.get("STALE_LOCK_ID"):
        raise RuntimeError("The reviewed lock no longer exists; stop and inspect before rerunning")
    for address, identifier in imports:
        require_time(240)
        print("Importing " + address, flush=True)
        print(run("terraform", "import", "-input=false", "-no-color", "-lock-timeout=60s", address, identifier), flush=True)
    after = json.loads(run("terraform", "state", "pull"))
    if missing_imports(state_instances(after)):
        raise RuntimeError("Recovery verification failed")
    print("All incident resource bindings are present. No infrastructure apply was run.", flush=True)
    require_time(240)
    print(run("terraform", "plan", "-input=false", "-no-color", "-lock-timeout=60s", "-out=recovery-review.tfplan"), flush=True)
    plan = json.loads(run("terraform", "show", "-json", "recovery-review.tfplan"))
    deletions = [item["address"] for item in plan.get("resource_changes", [])
                 if "delete" in item["change"]["actions"]]
    if deletions:
        raise RuntimeError("Plan includes destruction/replacement; inspect before continuing: " + ", ".join(deletions))
    print("Review-only plan contains no resource deletions or replacements. Inspect additions before resuming normal deployment.", flush=True)


if __name__ == "__main__":
    main()
