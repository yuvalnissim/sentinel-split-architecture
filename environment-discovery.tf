data "aws_iam_policy_document" "runner_environment_discovery" {
  statement {
    sid       = "DiscoverBackendALBSecurityGroup"
    effect    = "Allow"
    actions   = ["ec2:DescribeSecurityGroups"]
    resources = ["*"]

    # EC2 DescribeSecurityGroups cannot be scoped to individual group ARNs.
    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }
}

resource "aws_iam_role_policy" "runner_environment_discovery" {
  name   = "sentinel-environment-discovery"
  role   = module.runner_iam.role_name
  policy = data.aws_iam_policy_document.runner_environment_discovery.json
}
