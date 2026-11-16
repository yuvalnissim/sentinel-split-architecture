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

    def test_passrole_is_not_wildcard(self):
        statement = self.statements["PassOnlyExistingWorkloadRoles"]
        self.assertEqual(len(statement["Resource"]), 6)
        self.assertTrue(all("*" not in role for role in statement["Resource"]))
        self.assertIn("iam:PassedToService", statement["Condition"]["StringEquals"])


if __name__ == "__main__":
    unittest.main()
