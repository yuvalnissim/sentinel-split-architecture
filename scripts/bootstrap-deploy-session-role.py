"""Bootstrap a completion-only role for the recovered Sentinel environment.

This intentionally does not grant general Terraform provisioning/destruction.
Run only through the manual bootstrap GitHub Actions workflow.
"""
import json
import os
import subprocess

ACCOUNT = "485378272094"
REGION = "eu-north-1"
ROLE = "sentinel-terraform-deployer"
PROJECT = "sentinel-split-architecture"
SOURCE = f"arn:aws:iam::{ACCOUNT}:role/managed/AccountFullAccessRole"
POLICY_NAME = "sentinel-complete-recovered-environment"
BUCKET = f"sentinel-tfstate-{ACCOUNT}-{REGION}"


def aws(service, operation, *args):
    result = subprocess.run(
        ["aws", service, operation, *args, "--region", REGION,
         "--output", "json", "--no-cli-pager"],
        capture_output=True, text=True, timeout=90,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout) if result.stdout.strip() else {}


def trust_policy():
    return {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": {"AWS": SOURCE},
        "Action": "sts:AssumeRole",
    }]}


def completion_policy(cluster_sgs, alb_sg, volume_id, installer_entries=()):
    cluster_arns = [f"arn:aws:eks:{REGION}:{ACCOUNT}:cluster/eks-{d}"
                    for d in ("gateway", "backend")]
    subresources = [f"arn:aws:eks:{REGION}:{ACCOUNT}:{kind}/eks-{d}/*"
                    for d in ("gateway", "backend")
                    for kind in ("nodegroup", "addon", "access-entry",
                                 "podidentityassociation")]
    roles = [f"arn:aws:iam::{ACCOUNT}:role/{name}" for name in (
        "eks-gateway-nodes-role", "eks-backend-nodes-role",
        "sentinel-eks-gateway-cni", "sentinel-eks-backend-cni",
        "sentinel-eks-gateway-lb-controller", "sentinel-eks-backend-lb-controller",
    )]
    statements = []

    def allow(sid, actions, resources, condition=None):
        item = {"Sid": sid, "Effect": "Allow", "Action": actions,
                "Resource": resources}
        if condition:
            item["Condition"] = condition
        statements.append(item)

    allow("ReadRegionalNetworkInventory", ["ec2:Describe*"], ["*"],
          {"StringEquals": {"aws:RequestedRegion": REGION}})
    allow("ReadProjectIAM", ["iam:GetRole", "iam:GetRolePolicy", "iam:ListRolePolicies",
          "iam:ListAttachedRolePolicies", "iam:ListRoleTags", "iam:GetInstanceProfile"],
          [f"arn:aws:iam::{ACCOUNT}:role/eks-*",
           f"arn:aws:iam::{ACCOUNT}:role/sentinel-*",
           f"arn:aws:iam::{ACCOUNT}:instance-profile/sentinel-*"])
    allow("ReadExistingNodegroupServiceRole", ["iam:GetRole"],
          [f"arn:aws:iam::{ACCOUNT}:role/aws-service-role/eks-nodegroup.amazonaws.com/AWSServiceRoleForAmazonEKSNodegroup"])
    allow("ReadReferencedPolicies", ["iam:GetPolicy", "iam:GetPolicyVersion",
          "iam:ListPolicyVersions", "iam:ListPolicyTags"],
          [f"arn:aws:iam::{ACCOUNT}:policy/sentinel-*", "arn:aws:iam::aws:policy/*"])
    allow("ReadProjectEKS", ["eks:DescribeCluster", "eks:DescribeNodegroup",
          "eks:DescribeAddon", "eks:DescribeAccessEntry", "eks:DescribePodIdentityAssociation",
          "eks:DescribeUpdate", "eks:ListAccessEntries", "eks:ListAssociatedAccessPolicies",
          "eks:ListAddons", "eks:ListNodegroups", "eks:ListPodIdentityAssociations",
          "eks:ListTagsForResource", "eks:ListUpdates"], cluster_arns + subresources)
    allow("ReadAddonCatalog", ["eks:DescribeAddonVersions", "eks:DescribeAddonConfiguration"], ["*"])
    allow("CompleteExistingClusters", ["eks:CreateNodegroup", "eks:CreateAddon",
          "eks:CreateAccessEntry", "eks:CreatePodIdentityAssociation"], cluster_arns)
    allow("ConfigureExistingClusterResources", ["eks:AssociateAccessPolicy", "eks:TagResource",
          "eks:UpdateAddon", "eks:UpdatePodIdentityAssociation"], cluster_arns + subresources)
    allow("PassOnlyExistingWorkloadRoles", ["iam:PassRole"], roles,
          {"StringEquals": {"iam:PassedToService": ["eks.amazonaws.com", "pods.eks.amazonaws.com"]}})
    allow("InstallRunnerClusterDiscoveryPolicy", ["iam:PutRolePolicy"],
          [f"arn:aws:iam::{ACCOUNT}:role/sentinel-private-runner"])
    allow("RemoveOnlyTemporaryNodeCniPolicy", ["iam:DetachRolePolicy"],
          [f"arn:aws:iam::{ACCOUNT}:role/eks-{d}-nodes-role" for d in ("gateway", "backend")],
          {"ArnEquals": {"iam:PolicyARN": "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"}})
    allow("RemoveTemporaryInstallerRole", ["iam:DeleteRole", "iam:ListInstanceProfilesForRole"],
          [f"arn:aws:iam::{ACCOUNT}:role/sentinel-controller-installer"])
    # IAM cannot restrict DeleteRolePolicy by inline-policy name. Only the
    # existing runner role is authorized; Terraform removes the installer link.
    allow("RemoveRunnerInstallerLink", ["iam:DeleteRolePolicy"],
          [f"arn:aws:iam::{ACCOUNT}:role/sentinel-private-runner"])
    if installer_entries:
        allow("RemoveOnlyDiscoveredInstallerAccess", ["eks:DeleteAccessEntry",
              "eks:DisassociateAccessPolicy"], list(installer_entries))
    allow("CompleteNetworkRules", ["ec2:AuthorizeSecurityGroupIngress",
          "ec2:AuthorizeSecurityGroupEgress"],
          [f"arn:aws:ec2:{REGION}:{ACCOUNT}:security-group/{sg}"
           for sg in sorted(set(cluster_sgs + [alb_sg]))])
    # Tagged rule creation authorizes BOTH the parent group and the new rule.
    # Parent groups remain restricted by CompleteNetworkRules above.
    allow("AuthorizeNewNetworkRuleResources", ["ec2:AuthorizeSecurityGroupIngress",
          "ec2:AuthorizeSecurityGroupEgress"],
          [f"arn:aws:ec2:{REGION}:{ACCOUNT}:security-group-rule/*"],
          {"StringEquals": {"aws:RequestTag/Project": PROJECT}})
    allow("TagNewNetworkRules", ["ec2:CreateTags"],
          [f"arn:aws:ec2:{REGION}:{ACCOUNT}:security-group-rule/*"],
          {"StringEquals": {"aws:RequestTag/Project": PROJECT}})
    allow("ReconcileImportedRunnerVolumeTags", ["ec2:DeleteTags"],
          [f"arn:aws:ec2:{REGION}:{ACCOUNT}:volume/{volume_id}"],
          {"ForAllValues:StringEquals": {"aws:TagKeys": ["ManagedBy", "Project"]}})
    allow("ReadRegistryConfiguration", ["ecr:DescribeRepositories", "ecr:ListTagsForResource",
          "ecr:GetLifecyclePolicy", "ecr:GetRepositoryPolicy"],
          [f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/sentinel/*"])
    allow("ReadRunnerImageParameter", ["ssm:GetParameter"],
          [f"arn:aws:ssm:{REGION}::parameter/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"])
    allow("ListStatePrefix", ["s3:ListBucket"], [f"arn:aws:s3:::{BUCKET}"],
          {"StringLike": {"s3:prefix": ["sentinel/*"]}})
    allow("ReadWriteOnlyStateAndLock", ["s3:GetObject", "s3:PutObject"],
          [f"arn:aws:s3:::{BUCKET}/sentinel/terraform.tfstate",
           f"arn:aws:s3:::{BUCKET}/sentinel/terraform.tfstate.tflock"])
    allow("ReleaseOnlyStateLock", ["s3:DeleteObject"],
          [f"arn:aws:s3:::{BUCKET}/sentinel/terraform.tfstate.tflock"])
    return {"Version": "2012-10-17", "Statement": statements}


def main():
    if os.environ.get("CONFIRMATION") != "CREATE-SENTINEL-DEPLOY-ROLE":
        raise RuntimeError("Explicit bootstrap confirmation required")
    identity = aws("sts", "get-caller-identity")
    if identity["Account"] != ACCOUNT or not identity["Arn"].startswith(
            f"arn:aws:sts::{ACCOUNT}:assumed-role/AccountFullAccessRole/"):
        raise RuntimeError("Expected the reviewed bootstrap account and role")
    # STS session ARNs omit the IAM role path; resolve the full IAM ARN.
    source_role = aws("iam", "get-role", "--role-name", "AccountFullAccessRole")["Role"]
    if source_role["Arn"] != SOURCE:
        raise RuntimeError("Bootstrap role ARN differs from the reviewed trust principal")
    clusters = [aws("eks", "describe-cluster", "--name", f"eks-{d}")["cluster"]
                for d in ("gateway", "backend")]
    expected_vpcs = ["vpc-00127c0d370f4e9b2", "vpc-08829c8d48837184a"]
    if [c["resourcesVpcConfig"]["vpcId"] for c in clusters] != expected_vpcs:
        raise RuntimeError("This completion role is only for the recovered environment")
    groups = aws("ec2", "describe-security-groups", "--filters",
                 f"Name=vpc-id,Values={expected_vpcs[1]}",
                 "Name=group-name,Values=sentinel-backend-alb")["SecurityGroups"]
    if len(groups) != 1:
        raise RuntimeError("Expected exactly one backend ALB security group")
    instance = aws("ec2", "describe-instances", "--instance-ids", "i-0138e5cfebfd91401")["Reservations"][0]["Instances"][0]
    if instance["VpcId"] != expected_vpcs[0]:
        raise RuntimeError("Unexpected runner VPC")
    root = [b["Ebs"]["VolumeId"] for b in instance["BlockDeviceMappings"]
            if b["DeviceName"] == instance["RootDeviceName"]]
    if len(root) != 1:
        raise RuntimeError("Expected one root volume")
    installer_entries = []
    for cluster in clusters:
        try:
            entry = aws("eks", "describe-access-entry", "--cluster-name", cluster["name"],
                        "--principal-arn", f"arn:aws:iam::{ACCOUNT}:role/sentinel-controller-installer")["accessEntry"]
        except RuntimeError as error:
            if "ResourceNotFoundException" not in str(error):
                raise
        else:
            installer_entries.append(entry["accessEntryArn"])
    policy = completion_policy([c["resourcesVpcConfig"]["clusterSecurityGroupId"]
                                for c in clusters], groups[0]["GroupId"], root[0], installer_entries)
    encoded_policy = json.dumps(policy, separators=(",", ":"))
    if len(encoded_policy) > 10240:
        raise RuntimeError("Inline role policy exceeds IAM size limit")
    # Check existence via an exact get; never interpret AccessDenied as absence.
    try:
        existing = aws("iam", "get-role", "--role-name", ROLE)["Role"]
    except RuntimeError as error:
        if "NoSuchEntity" not in str(error):
            raise
        existing = None
    if existing:
        tags = {t["Key"]: t["Value"] for t in existing.get("Tags", [])}
        if tags.get("Purpose") != "sentinel-recovery-completion" or existing["AssumeRolePolicyDocument"] != trust_policy():
            raise RuntimeError("Refusing to overwrite an unrecognized existing role")
        inline = aws("iam", "list-role-policies", "--role-name", ROLE)["PolicyNames"]
        attached = aws("iam", "list-attached-role-policies", "--role-name", ROLE)["AttachedPolicies"]
        if set(inline) - {POLICY_NAME} or attached:
            raise RuntimeError("Unexpected additional permissions on completion role")
    else:
        aws("iam", "create-role", "--role-name", ROLE,
            "--assume-role-policy-document", json.dumps(trust_policy()),
            "--max-session-duration", "3600", "--tags",
            f"Key=Project,Value={PROJECT}", "Key=Purpose,Value=sentinel-recovery-completion")
    aws("iam", "put-role-policy", "--role-name", ROLE,
        "--policy-name", POLICY_NAME, "--policy-document", encoded_policy)
    print(f"Prepared arn:aws:iam::{ACCOUNT}:role/{ROLE}; no Terraform apply was run.")
    print("Completion only: no cluster deletion, role self-modification, or general infrastructure creation.")


if __name__ == "__main__":
    main()
