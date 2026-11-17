import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "deploy_role", Path(__file__).parents[1] / "scripts/bootstrap-deploy-session-role.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CompletionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = module.completion_policy(["sg-gateway", "sg-backend"], "sg-alb", "vol-root")
        self.statements = {s["Sid"]: s for s in self.policy["Statement"]}

    def test_does_not_grant_general_provisioning_or_self_escalation(self):
        actions = {a for s in self.policy["Statement"] for a in s["Action"]}
        for action in ("eks:DeleteCluster", "eks:CreateCluster", "iam:CreateRole",
                       "iam:AttachRolePolicy", "iam:UpdateAssumeRolePolicy",
                       "ec2:RunInstances", "s3:DeleteBucket"):
            self.assertNotIn(action, actions)
        for statement in self.policy["Statement"]:
            for action in statement["Action"]:
                if not (action.startswith("ec2:Describe") or "Read" in statement["Sid"]):
                    self.assertNotEqual(statement["Resource"], ["*"])

    def test_trust_is_only_existing_bootstrap_role(self):
        statement = module.trust_policy()["Statement"][0]
        self.assertEqual(statement["Principal"], {"AWS": module.SOURCE})
        self.assertEqual(statement["Action"], "sts:AssumeRole")

    def test_can_delete_lock_but_not_state(self):
        targets = self.statements["ReleaseOnlyStateLock"]["Resource"]
        self.assertEqual(targets, [f"arn:aws:s3:::{module.BUCKET}/sentinel/terraform.tfstate.tflock"])
        self.assertNotIn("s3:DeleteObject", self.statements["ReadWriteOnlyStateAndLock"]["Action"])

    def test_mutable_security_groups_and_volume_are_exact(self):
        resources = self.statements["CompleteNetworkRules"]["Resource"]
        self.assertEqual(len(resources), 3)
        self.assertTrue(all("*" not in resource for resource in resources))
        self.assertTrue(self.statements["ReconcileImportedRunnerVolumeTags"]["Resource"][0].endswith("/vol-root"))

    def test_tagged_creation_authorizes_both_resource_types(self):
        parent = self.statements["CompleteNetworkRules"]
        rule = self.statements["AuthorizeNewNetworkRuleResources"]
        self.assertEqual(set(parent["Action"]), set(rule["Action"]))
        self.assertTrue(all("security-group/sg-" in r for r in parent["Resource"]))
        self.assertEqual(rule["Resource"], [f"arn:aws:ec2:{module.REGION}:{module.ACCOUNT}:security-group-rule/*"])
        self.assertEqual(rule["Condition"]["StringEquals"]["aws:RequestTag/Project"], module.PROJECT)

    def test_service_linked_role_is_read_only_and_exact(self):
        statement = self.statements["ReadExistingNodegroupServiceRole"]
        self.assertEqual(statement["Action"], ["iam:GetRole"])
        self.assertEqual(statement["Resource"], [f"arn:aws:iam::{module.ACCOUNT}:role/aws-service-role/eks-nodegroup.amazonaws.com/AWSServiceRoleForAmazonEKSNodegroup"])
        for other in self.policy["Statement"]:
            if other["Sid"] != statement["Sid"]:
                self.assertFalse(any("aws-service-role/" in r for r in other["Resource"]))

    def test_cni_detach_cannot_remove_other_node_policies(self):
        statement = self.statements["RemoveOnlyTemporaryNodeCniPolicy"]
        self.assertEqual(statement["Action"], ["iam:DetachRolePolicy"])
        self.assertEqual(len(statement["Resource"]), 2)
        self.assertTrue(all(r.endswith("-nodes-role") and "*" not in r for r in statement["Resource"]))
        self.assertEqual(statement["Condition"]["ArnEquals"]["iam:PolicyARN"],
                         "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy")

    def test_installer_cleanup_requires_discovered_access_entries(self):
        self.assertNotIn("RemoveOnlyDiscoveredInstallerAccess", self.statements)
        arn = f"arn:aws:eks:{module.REGION}:{module.ACCOUNT}:access-entry/eks-gateway/role/{module.ACCOUNT}/sentinel-controller-installer/example"
        policy = module.completion_policy(["sg-gateway", "sg-backend"], "sg-alb", "vol-root", [arn])
        statement = next(s for s in policy["Statement"] if s["Sid"] == "RemoveOnlyDiscoveredInstallerAccess")
        self.assertEqual(statement["Resource"], [arn])
        self.assertEqual(set(statement["Action"]), {"eks:DeleteAccessEntry", "eks:DisassociateAccessPolicy"})
        role = self.statements["RemoveTemporaryInstallerRole"]
        self.assertEqual(role["Resource"], [f"arn:aws:iam::{module.ACCOUNT}:role/sentinel-controller-installer"])

    def test_passrole_is_not_wildcard(self):
        statement = self.statements["PassOnlyExistingWorkloadRoles"]
        self.assertEqual(len(statement["Resource"]), 6)
        self.assertTrue(all("*" not in role for role in statement["Resource"]))
        self.assertIn("iam:PassedToService", statement["Condition"]["StringEquals"])


if __name__ == "__main__":
    unittest.main()
