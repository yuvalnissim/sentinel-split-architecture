data "aws_iam_policy_document" "runner_ecr" {
  statement {
    sid       = "AuthenticateToECR"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid    = "PushAndPullSentinelImages"
    effect = "Allow"

    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
      "ecr:DescribeImages",
    ]

    resources = [
      for repository in module.registry : repository.repository_arn
    ]
  }
}

resource "aws_iam_role_policy" "runner_ecr" {
  name   = "sentinel-runner-ecr"
  role   = module.runner_iam.role_name
  policy = data.aws_iam_policy_document.runner_ecr.json
}