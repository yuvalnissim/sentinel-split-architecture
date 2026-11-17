"""Create an incident-scoped teardown identity from private remote state.

No workloads or Terraform-managed resources are deleted by this script.
"""
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile

spec = importlib.util.spec_from_file_location("bootstrap", Path(__file__).with_name("bootstrap-deploy-session-role.py"))
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)
aws = bootstrap.aws
ACCOUNT, REGION, BUCKET = bootstrap.ACCOUNT, bootstrap.REGION, bootstrap.BUCKET
ROLE = "sentinel-terraform-teardown"
POLICY = "sentinel-destroy-recovered-environment"
VPCS = {"vpc-00127c0d370f4e9b2", "vpc-08829c8d48837184a"}
SUPPORTED = set("""aws_ecr_repository aws_eip aws_eks_access_entry
aws_eks_access_policy_association aws_eks_addon aws_eks_cluster aws_eks_node_group
aws_eks_pod_identity_association aws_iam_instance_profile aws_iam_policy aws_iam_role
aws_iam_role_policy aws_iam_role_policy_attachment aws_instance aws_internet_gateway
aws_nat_gateway aws_route aws_route_table aws_route_table_association aws_security_group
aws_subnet aws_vpc aws_vpc_peering_connection aws_vpc_security_group_egress_rule
aws_vpc_security_group_ingress_rule""".split())


def inventory(state):
    result = {}
    for resource in state.get("resources", []):
        if resource["mode"] != "managed":
            continue
        kind = resource["type"]
        if kind not in SUPPORTED:
            raise RuntimeError(f"Unreviewed resource type: {kind}")
        for instance in resource.get("instances", []):
            if instance.get("deposed"):
                raise RuntimeError("Deposed state requires review before teardown")
            result.setdefault(kind, []).append(instance["attributes"])
    if {a["id"] for a in result.get("aws_vpc", [])} != VPCS:
        raise RuntimeError("State does not match the two recovered VPCs")
    if {a["name"] for a in result.get("aws_eks_cluster", [])} != {"eks-gateway", "eks-backend"}:
        raise RuntimeError("State does not match the two project clusters")
    for kind in ("aws_iam_role", "aws_iam_instance_profile", "aws_iam_policy"):
        for item in result.get(kind, []):
            if not item["name"].startswith(("eks-", "sentinel-")):
                raise RuntimeError("IAM resource outside approved naming prefixes")
    return result


def policy_for(state, groups):
    items = inventory(state)
    statements = []

    def allow(sid, actions, resources, condition=None):
        resources = sorted(set(resources))
        if not resources:
            return
        entry = {"Sid": sid, "Effect": "Allow", "Action": actions, "Resource": resources}
        if condition:
            entry["Condition"] = condition
        statements.append(entry)

    def ec2(kind, value):
        if not re.fullmatch(r"[a-z]+-[0-9a-f]+", value):
            raise RuntimeError(f"Unexpected EC2 identifier: {value}")
        return f"arn:aws:ec2:{REGION}:{ACCOUNT}:{kind}/{value}"

    def iam_arns(kind, resource):
        output = []
        prefix = f"arn:aws:iam::{ACCOUNT}:{resource}/"
        for item in items.get(kind, []):
            arn = item["arn"]
            if not arn.startswith(prefix):
                raise RuntimeError("Unexpected IAM resource ARN")
            output.append(arn)
        return output

    roles = iam_arns("aws_iam_role", "role")
    profiles = iam_arns("aws_iam_instance_profile", "instance-profile")
    policies = iam_arns("aws_iam_policy", "policy")
    if any(a.endswith("/" + ROLE) or a.endswith("/sentinel-terraform-deployer") for a in roles):
        raise RuntimeError("Bootstrap identities must not be included in root teardown state")
    allow("ReadRegionalNetworkInventory", ["ec2:Describe*"], ["*"],
          {"StringEquals": {"aws:RequestedRegion": REGION}})
    allow("ReadLoadBalancerInventory", ["elasticloadbalancing:DescribeLoadBalancers",
          "elasticloadbalancing:DescribeTargetGroups"], ["*"],
          {"StringEquals": {"aws:RequestedRegion": REGION}})
    allow("ReadStateIAMRoles", ["iam:GetRole", "iam:ListRolePolicies", "iam:GetRolePolicy",
          "iam:ListAttachedRolePolicies", "iam:ListRoleTags", "iam:ListInstanceProfilesForRole"], roles)
    allow("ReadNodegroupServiceRole", ["iam:GetRole"],
          [f"arn:aws:iam::{ACCOUNT}:role/aws-service-role/eks-nodegroup.amazonaws.com/AWSServiceRoleForAmazonEKSNodegroup"])
    allow("ReadStateProfiles", ["iam:GetInstanceProfile"], profiles)
    allow("ReadStatePolicies", ["iam:GetPolicy", "iam:GetPolicyVersion",
          "iam:ListPolicyVersions", "iam:ListPolicyTags"], policies + ["arn:aws:iam::aws:policy/*"])
    allow("DeleteStateIAMRolesAndLinks", ["iam:DeleteRole", "iam:DeleteRolePolicy",
          "iam:DetachRolePolicy"], roles)
    allow("DeleteStateProfiles", ["iam:RemoveRoleFromInstanceProfile", "iam:DeleteInstanceProfile"], profiles)
    allow("DeleteStateManagedPolicies", ["iam:DeletePolicy", "iam:DeletePolicyVersion"], policies)
    eks_resources = [f"arn:aws:eks:{REGION}:{ACCOUNT}:cluster/eks-{d}" for d in ("gateway", "backend")]
    eks_resources += [f"arn:aws:eks:{REGION}:{ACCOUNT}:{kind}/eks-{d}/*"
                      for d in ("gateway", "backend")
                      for kind in ("nodegroup", "addon", "access-entry", "podidentityassociation")]
    allow("ReadAndDeleteProjectEKS", ["eks:DescribeCluster", "eks:DescribeNodegroup", "eks:DescribeAddon",
          "eks:DescribeAccessEntry", "eks:DescribePodIdentityAssociation", "eks:DescribeUpdate",
          "eks:ListAccessEntries", "eks:ListAssociatedAccessPolicies", "eks:ListAddons",
          "eks:ListNodegroups", "eks:ListPodIdentityAssociations", "eks:ListTagsForResource", "eks:ListUpdates",
          "eks:DeleteCluster", "eks:DeleteNodegroup", "eks:DeleteAddon", "eks:DeleteAccessEntry",
          "eks:DisassociateAccessPolicy", "eks:DeletePodIdentityAssociation"], eks_resources)
    allow("ReadAddonCatalog", ["eks:DescribeAddonVersions", "eks:DescribeAddonConfiguration"], ["*"])
    registry = []
    for item in items.get("aws_ecr_repository", []):
        if item["name"] not in ("sentinel/backend", "sentinel/gateway"):
            raise RuntimeError("Unexpected registry repository")
        registry.append(f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/{item['name']}")
    allow("ReadAndDeleteProjectRegistry", ["ecr:DescribeRepositories", "ecr:GetRepositoryPolicy",
          "ecr:GetLifecyclePolicy", "ecr:ListTagsForResource", "ecr:DeleteRepository"], registry)
    mappings = {
        "aws_vpc": ("vpc", ["ec2:DeleteVpc"]),
        "aws_subnet": ("subnet", ["ec2:DeleteSubnet"]),
        "aws_route_table": ("route-table", ["ec2:DeleteRouteTable", "ec2:DeleteRoute", "ec2:DisassociateRouteTable"]),
        "aws_internet_gateway": ("internet-gateway", ["ec2:DetachInternetGateway", "ec2:DeleteInternetGateway"]),
        "aws_nat_gateway": ("natgateway", ["ec2:DeleteNatGateway"]),
        "aws_eip": ("elastic-ip", ["ec2:ReleaseAddress"]),
        "aws_vpc_peering_connection": ("vpc-peering-connection", ["ec2:DeleteVpcPeeringConnection"]),
        "aws_instance": ("instance", ["ec2:TerminateInstances"]),
    }
    for kind, (arn_kind, actions) in mappings.items():
        allow("Delete" + kind.replace("_", ""), actions, [ec2(arn_kind, a["id"]) for a in items.get(kind, [])])
    # These APIs authorize all participating resource types, not only the
    # primary gateway/route-table ARN.
    allow("DetachOnlyStateGatewaysFromStateVpcs", ["ec2:DetachInternetGateway"],
          [ec2("vpc", a["id"]) for a in items.get("aws_vpc", [])])
    allow("DisassociateOnlyStateSubnets", ["ec2:DisassociateRouteTable"],
          [ec2("subnet", a["id"]) for a in items.get("aws_subnet", [])])
    state_sgs = {a["id"] for a in items.get("aws_security_group", [])}
    controller_sgs, cluster_sgs = set(), {a["vpc_config"][0]["cluster_security_group_id"] for a in items["aws_eks_cluster"]}
    for group in groups:
        if group["VpcId"] not in VPCS:
            continue
        tags = {t["Key"]: t["Value"] for t in (group.get("Tags") or [])}
        if tags.get("elbv2.k8s.aws/cluster") in ("eks-gateway", "eks-backend") and tags.get("elbv2.k8s.aws/resource") == "backend-sg":
            controller_sgs.add(group["GroupId"])
    allowed_groups = state_sgs | controller_sgs | cluster_sgs
    allow("DeleteStateAndControllerGroups", ["ec2:DeleteSecurityGroup"], [ec2("security-group", g) for g in state_sgs | controller_sgs])
    allow("RevokeProjectNetworkRules", ["ec2:RevokeSecurityGroupIngress", "ec2:RevokeSecurityGroupEgress"],
          [ec2("security-group", g) for g in allowed_groups])
    allow("ReadRunnerImageParameter", ["ssm:GetParameter"],
          [f"arn:aws:ssm:{REGION}::parameter/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"])
    allow("ListStatePrefix", ["s3:ListBucket"], [f"arn:aws:s3:::{BUCKET}"],
          {"StringLike": {"s3:prefix": ["sentinel/*"]}})
    allow("ReadWriteStateAndLock", ["s3:GetObject", "s3:PutObject"],
          [f"arn:aws:s3:::{BUCKET}/sentinel/terraform.tfstate", f"arn:aws:s3:::{BUCKET}/sentinel/terraform.tfstate.tflock"])
    allow("WriteEmergencyStateBackup", ["s3:PutObject"],
          [f"arn:aws:s3:::{BUCKET}/sentinel/recovery/*"],
          {"StringEquals": {"s3:x-amz-server-side-encryption": "AES256"}})
    allow("ReleaseOnlyStateLock", ["s3:DeleteObject"], [f"arn:aws:s3:::{BUCKET}/sentinel/terraform.tfstate.tflock"])
    return {"Version": "2012-10-17", "Statement": statements}


def main():
    if os.environ.get("CONFIRMATION") != "PREPARE-SENTINEL-TEARDOWN":
        raise RuntimeError("Explicit role-preparation confirmation required")
    identity = aws("sts", "get-caller-identity")
    if identity["Account"] != ACCOUNT or not identity["Arn"].startswith(f"arn:aws:sts::{ACCOUNT}:assumed-role/AccountFullAccessRole/"):
        raise RuntimeError("Unexpected bootstrap identity")
    if aws("iam", "get-role", "--role-name", "AccountFullAccessRole")["Role"]["Arn"] != bootstrap.SOURCE:
        raise RuntimeError("Unexpected source IAM role ARN")
    with tempfile.TemporaryDirectory() as directory:
        filename = str(Path(directory) / "state.json")
        aws("s3api", "get-object", "--bucket", BUCKET, "--expected-bucket-owner", ACCOUNT,
            "--key", "sentinel/terraform.tfstate", filename)
        state = json.loads(Path(filename).read_text())
    inventory(state)
    groups = aws("ec2", "describe-security-groups", "--filters", "Name=vpc-id,Values=" + ",".join(sorted(VPCS)))["SecurityGroups"]
    policy = policy_for(state, groups)
    encoded = json.dumps(policy, separators=(",", ":"))
    if len(encoded) > 10240:
        raise RuntimeError("Policy exceeds IAM inline limit; review required")
    try:
        existing = aws("iam", "get-role", "--role-name", ROLE)["Role"]
    except RuntimeError as error:
        if "NoSuchEntity" not in str(error):
            raise
        existing = None
    if existing:
        tags = {t["Key"]: t["Value"] for t in existing.get("Tags", [])}
        if tags.get("Purpose") != "sentinel-recovered-teardown" or existing["AssumeRolePolicyDocument"] != bootstrap.trust_policy():
            raise RuntimeError("Refusing to overwrite unrecognized teardown role")
        if set(aws("iam", "list-role-policies", "--role-name", ROLE)["PolicyNames"]) - {POLICY}:
            raise RuntimeError("Unexpected inline policies")
        if aws("iam", "list-attached-role-policies", "--role-name", ROLE)["AttachedPolicies"]:
            raise RuntimeError("Unexpected managed policies")
    else:
        aws("iam", "create-role", "--role-name", ROLE, "--max-session-duration", "3600",
            "--assume-role-policy-document", json.dumps(bootstrap.trust_policy()),
            "--tags", f"Key=Project,Value={bootstrap.PROJECT}", "Key=Purpose,Value=sentinel-recovered-teardown")
    aws("iam", "put-role-policy", "--role-name", ROLE, "--policy-name", POLICY, "--policy-document", encoded)
    print(f"Prepared arn:aws:iam::{ACCOUNT}:role/{ROLE}; no application or infrastructure deletion was run.")


if __name__ == "__main__":
    main()
