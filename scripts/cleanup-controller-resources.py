import json
import subprocess
import time

REGION = "eu-north-1"
ACCOUNT = "485378272094"

CLUSTERS = {
    "eks-gateway": "vpc-0940cc90a288b5995",
    "eks-backend": "vpc-0349516895f0bda08",
}
VPCS = set(CLUSTERS.values())


def aws(service, operation, *arguments):
    command = [
        "aws", service, operation,
        "--region", REGION,
        "--output", "json",
        "--no-cli-pager",
        *arguments,
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout) if result.stdout.strip() else {}


identity = aws("sts", "get-caller-identity")
if identity["Account"] != ACCOUNT:
    raise RuntimeError("Unexpected AWS account.")

# Controllers must finish deleting load balancers and target groups first.
deadline = time.monotonic() + 900

while True:
    load_balancers = [
        item
        for item in aws(
            "elbv2", "describe-load-balancers"
        )["LoadBalancers"]
        if item["VpcId"] in VPCS
    ]

    target_groups = [
        item
        for item in aws(
            "elbv2", "describe-target-groups"
        )["TargetGroups"]
        if item["VpcId"] in VPCS
    ]

    print(
        f"Remaining project load balancers: {len(load_balancers)}; "
        f"target groups: {len(target_groups)}",
        flush=True,
    )

    if not load_balancers and not target_groups:
        break

    if time.monotonic() >= deadline:
        raise RuntimeError(
            "Load balancers or target groups remain. "
            "Infrastructure destruction is blocked."
        )

    time.sleep(15)

groups = aws(
    "ec2",
    "describe-security-groups",
    "--filters",
    "Name=vpc-id,Values=" + ",".join(sorted(VPCS)),
)["SecurityGroups"]

groups_by_id = {group["GroupId"]: group for group in groups}
shared_groups = []

for group in groups:
    tags = {
        tag["Key"]: tag["Value"]
        for tag in (group.get("Tags") or [])
    }

    cluster = tags.get("elbv2.k8s.aws/cluster")
    if cluster not in CLUSTERS:
        continue

    if group["VpcId"] != CLUSTERS[cluster]:
        raise RuntimeError("Controller security group VPC mismatch.")

    if tags.get("ingress.k8s.aws/resource") == "ManagedLBSecurityGroup":
        raise RuntimeError(
            f"Controller frontend group still exists: {group['GroupId']}. "
            "Wait for controller cleanup before retrying."
        )

    if tags.get("elbv2.k8s.aws/resource") == "backend-sg":
        shared_groups.append(group)

# Prepare and validate the entire cleanup before removing any rules.
rules_to_remove = []

for shared_group in shared_groups:
    group_id = shared_group["GroupId"]

    interfaces = aws(
        "ec2",
        "describe-network-interfaces",
        "--filters",
        f"Name=group-id,Values={group_id}",
    )["NetworkInterfaces"]

    if interfaces:
        raise RuntimeError(
            f"Security group {group_id} is still attached to network interfaces."
        )

    referencing_rules = [
        rule
        for rule in aws(
            "ec2",
            "describe-security-group-rules",
        )["SecurityGroupRules"]
        if (rule.get("ReferencedGroupInfo") or {}).get("GroupId") == group_id
    ]

    for rule in referencing_rules:
        owner = groups_by_id.get(rule["GroupId"])
        description = rule.get("Description", "")

        if (
            owner is None
            or owner["VpcId"] != shared_group["VpcId"]
            or rule["IsEgress"]
            or not description.startswith(
                "elbv2.k8s.aws/targetGroupBinding"
            )
        ):
            raise RuntimeError(
                "Unexpected reference to controller security group: "
                f"{rule['SecurityGroupRuleId']}. "
                "Manual review is required."
            )

        rules_to_remove.append(rule)

for rule in rules_to_remove:
    print(
        f"Removing controller ingress rule {rule['SecurityGroupRuleId']}",
        flush=True,
    )
    aws(
        "ec2",
        "revoke-security-group-ingress",
        "--group-id",
        rule["GroupId"],
        "--security-group-rule-ids",
        rule["SecurityGroupRuleId"],
    )

for group in shared_groups:
    print(
        f"Deleting controller backend security group {group['GroupId']}",
        flush=True,
    )

    deadline = time.monotonic() + 180
    while True:
        try:
            aws(
                "ec2",
                "delete-security-group",
                "--group-id",
                group["GroupId"],
            )
            break
        except RuntimeError as error:
            if (
                "DependencyViolation" not in str(error)
                or time.monotonic() >= deadline
            ):
                raise
            time.sleep(10)

print("Controller resource cleanup completed.", flush=True)