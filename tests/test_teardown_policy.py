import copy
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("teardown", Path(__file__).parents[1] / "scripts/bootstrap-teardown-role.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def sample_state():
    resources = []
    def add(kind, **attributes):
        resources.append({"mode": "managed", "type": kind, "instances": [{"attributes": attributes}]})
    for i, domain in enumerate(("gateway", "backend"), 1):
        add("aws_vpc", id=sorted(module.VPCS)[i-1])
        add("aws_eks_cluster", name="eks-" + domain, vpc_config=[{"cluster_security_group_id": f"sg-00{i}"}])
        for name in (f"eks-{domain}-cluster-role", f"eks-{domain}-nodes-role", f"sentinel-eks-{domain}-cni", f"sentinel-eks-{domain}-lb-controller"):
            add("aws_iam_role", name=name, arn=f"arn:aws:iam::{module.ACCOUNT}:role/{name}")
        add("aws_iam_policy", name=f"sentinel-eks-{domain}-lb-controller", arn=f"arn:aws:iam::{module.ACCOUNT}:policy/sentinel-eks-{domain}-lb-controller")
        add("aws_ecr_repository", name="sentinel/" + domain)
        add("aws_security_group", id=f"sg-10{i}")
        for kind, prefix in (("aws_subnet", "subnet"), ("aws_route_table", "rtb"), ("aws_nat_gateway", "nat"), ("aws_eip", "eipalloc"), ("aws_internet_gateway", "igw")):
            for n in (1, 2):
                add(kind, id=f"{prefix}-000{i}{n}")
    add("aws_iam_role", name="sentinel-private-runner", arn=f"arn:aws:iam::{module.ACCOUNT}:role/sentinel-private-runner")
    add("aws_iam_instance_profile", name="sentinel-private-runner", arn=f"arn:aws:iam::{module.ACCOUNT}:instance-profile/sentinel-private-runner")
    add("aws_instance", id="i-0001")
    add("aws_vpc_peering_connection", id="pcx-0001")
    return {"resources": resources}


class TeardownPolicyTests(unittest.TestCase):
    def setUp(self):
        self.state = sample_state()
        self.policy = module.policy_for(self.state, [])
        self.statements = {s["Sid"]: s for s in self.policy["Statement"]}

    def test_unknown_state_and_other_vpc_fail_closed(self):
        invalid = copy.deepcopy(self.state)
        invalid["resources"].append({"mode": "managed", "type": "aws_s3_bucket", "instances": []})
        with self.assertRaises(RuntimeError):
            module.policy_for(invalid, [])
        invalid = copy.deepcopy(self.state)
        invalid["resources"][0]["instances"][0]["attributes"]["id"] = "vpc-ffff"
        with self.assertRaises(RuntimeError):
            module.policy_for(invalid, [])

    def test_no_creation_passrole_or_bootstrap_role_mutation(self):
        actions = {a for s in self.policy["Statement"] for a in s["Action"]}
        self.assertFalse(any(":Create" in a or ":PutRole" in a or a == "iam:PassRole" for a in actions))
        role_targets = self.statements["DeleteStateIAMRolesAndLinks"]["Resource"]
        self.assertTrue(all("terraform-deployer" not in r and "terraform-teardown" not in r and "AccountFullAccessRole" not in r for r in role_targets))
        for statement in self.policy["Statement"]:
            if any(":Delete" in a or ":Terminate" in a or ":Revoke" in a for a in statement["Action"]):
                self.assertNotEqual(statement["Resource"], ["*"])

    def test_existing_shared_group_only_in_project_vpc(self):
        def group(group_id, vpc):
            return {"GroupId": group_id, "VpcId": vpc, "Tags": [
                {"Key": "elbv2.k8s.aws/cluster", "Value": "eks-gateway"},
                {"Key": "elbv2.k8s.aws/resource", "Value": "backend-sg"}]}
        policy = module.policy_for(self.state, [group("sg-ffff", "vpc-ffff"), group("sg-aaaa", next(iter(module.VPCS)))])
        targets = next(s for s in policy["Statement"] if s["Sid"] == "DeleteStateAndControllerGroups")["Resource"]
        self.assertTrue(any(r.endswith("/sg-aaaa") for r in targets))
        self.assertFalse(any(r.endswith("/sg-ffff") for r in targets))

    def test_state_and_bucket_cannot_be_deleted(self):
        actions = {a for s in self.policy["Statement"] for a in s["Action"]}
        self.assertNotIn("s3:DeleteBucket", actions)
        self.assertEqual(self.statements["ReleaseOnlyStateLock"]["Resource"],
                         [f"arn:aws:s3:::{module.BUCKET}/sentinel/terraform.tfstate.tflock"])

    def test_policy_fits_inline_limit_with_representative_inventory(self):
        self.assertLess(len(json.dumps(self.policy, separators=(",", ":"))), 10240)


if __name__ == "__main__":
    unittest.main()
