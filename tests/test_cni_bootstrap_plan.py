import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "guard", Path(__file__).resolve().parents[1] / "scripts/check-cni-bootstrap-plan.py"
)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def node(domain="gateway", actions=None):
    return {
        "address": f'module.eks["{domain}"].aws_eks_node_group.this',
        "type": "aws_eks_node_group",
        "change": {"actions": actions or ["create"], "after": {}},
    }


def attachment(domain="gateway", actions=None):
    return {
        "address": f'module.eks["{domain}"].aws_iam_role_policy_attachment.cni_bootstrap[0]',
        "type": "aws_iam_role_policy_attachment",
        "name": "cni_bootstrap",
        "change": {
            "actions": actions or ["create"],
            "after": {"policy_arn": "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"},
        },
    }


class BootstrapGuardTests(unittest.TestCase):
    def check(self, changes):
        return guard.bootstrap_errors({"resource_changes": changes})

    def test_fresh_creation_without_permissions_is_blocked(self):
        self.assertEqual(self.check([node()]), [node()["address"]])

    def test_both_clusters_require_their_own_attachment(self):
        self.assertEqual(self.check([node(), node("backend"), attachment()]),
                         [node("backend")["address"]])

    def test_initial_creation_with_unknown_role_arn_is_allowed(self):
        self.assertEqual(self.check([node(), attachment()]), [])

    def test_replacement_requires_bootstrap(self):
        self.assertTrue(self.check([node(actions=["delete", "create"])]))

    def test_existing_attachment_can_support_replacement(self):
        self.assertEqual(self.check([node(actions=["create", "delete"]),
                                     attachment(actions=["no-op"])]), [])

    def test_deleting_attachment_does_not_allow_creation(self):
        self.assertTrue(self.check([node(), attachment(actions=["delete"])]))

    def test_wrong_policy_is_blocked(self):
        item = attachment()
        item["change"]["after"]["policy_arn"] = "wrong-policy"
        self.assertTrue(self.check([node(), item]))

    def test_steady_state_update_and_bootstrap_removal_are_allowed(self):
        self.assertEqual(self.check([node(actions=["update"]),
                                     attachment(actions=["delete"])]), [])

    def test_empty_state_is_allowed(self):
        self.assertEqual(self.check([]), [])


if __name__ == "__main__":
    unittest.main()
