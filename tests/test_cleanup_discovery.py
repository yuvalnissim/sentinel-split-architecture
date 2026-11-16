import contextlib
import io
import json
import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/cleanup-controller-resources.py"


class CleanupDiscoveryTests(unittest.TestCase):
    def execute(self, *, account="485378272094", missing_cluster=False, same_vpc=False):
        calls = []

        def fake_run(command, **kwargs):
            service, operation = command[1:3]
            calls.append((service, operation, command))
            if (service, operation) == ("sts", "get-caller-identity"):
                result = {"Account": account}
            elif (service, operation) == ("eks", "describe-cluster"):
                if missing_cluster:
                    return SimpleNamespace(returncode=1, stdout="", stderr="ResourceNotFoundException")
                name = command[command.index("--name") + 1]
                vpc = "vpc-aaa" if same_vpc or name == "eks-gateway" else "vpc-bbb"
                result = {"cluster": {"resourcesVpcConfig": {"vpcId": vpc}}}
            elif (service, operation) == ("elbv2", "describe-load-balancers"):
                result = {"LoadBalancers": []}
            elif (service, operation) == ("elbv2", "describe-target-groups"):
                result = {"TargetGroups": []}
            elif (service, operation) == ("ec2", "describe-security-groups"):
                self.assertIn("Name=vpc-id,Values=vpc-aaa,vpc-bbb", command)
                result = {"SecurityGroups": []}
            else:
                raise AssertionError(f"Unexpected AWS operation: {service} {operation}")
            return SimpleNamespace(returncode=0, stdout=json.dumps(result), stderr="")

        with patch("subprocess.run", side_effect=fake_run), contextlib.redirect_stdout(io.StringIO()):
            runpy.run_path(str(SCRIPT), run_name="__main__")
        return calls

    def test_cleanup_uses_current_cluster_vpcs(self):
        calls = self.execute()
        self.assertEqual(sum(operation == "describe-cluster" for _, operation, _ in calls), 2)
        self.assertTrue(all(operation.startswith("describe-") or operation == "get-caller-identity"
                            for _, operation, _ in calls))

    def test_wrong_account_aborts(self):
        with self.assertRaisesRegex(RuntimeError, "Unexpected AWS account"):
            self.execute(account="000000000000")

    def test_missing_cluster_aborts_before_cleanup(self):
        with self.assertRaisesRegex(RuntimeError, "ResourceNotFoundException"):
            self.execute(missing_cluster=True)

    def test_same_vpc_aborts_before_cleanup(self):
        with self.assertRaisesRegex(RuntimeError, "two distinct"):
            self.execute(same_vpc=True)


if __name__ == "__main__":
    unittest.main()
