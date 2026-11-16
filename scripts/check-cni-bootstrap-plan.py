"""Reject new EKS node groups without temporary CNI bootstrap permissions.

Read only a Terraform plan JSON from stdin; never print plan values, which
can include secrets. Exit nonzero before apply if bootstrap is missing.
"""
import json
import sys


def bootstrap_errors(plan):
    changes = plan.get("resource_changes", [])
    errors = []
    for item in changes:
        change = item.get("change", {})
        if item.get("type") != "aws_eks_node_group" or "create" not in change.get("actions", []):
            continue
        # Match module addresses as role values can be unknown on initial creation.
        parent = item["address"].rsplit(".aws_eks_node_group.", 1)[0]
        matching = any(
            attachment.get("address") == parent + ".aws_iam_role_policy_attachment.cni_bootstrap[0]"
            and attachment.get("change", {}).get("actions") != ["delete"]
            and (attachment.get("change", {}).get("after") or {}).get("policy_arn")
            == "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
            for attachment in changes
        )
        if not matching:
            errors.append(item["address"])
    return errors


def main():
    errors = bootstrap_errors(json.load(sys.stdin))
    if errors:
        print("New or replacement EKS node groups require CNI bootstrap permissions:", file=sys.stderr)
        for address in errors:
            print(address, file=sys.stderr)
        print("Run Terraform deploy manually with enable_cni_bootstrap=true. "
              "Verify CNI Pod Identity before disabling bootstrap.", file=sys.stderr)
        return 1
    print("CNI bootstrap plan check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
