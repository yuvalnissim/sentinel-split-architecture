locals {
  # Temporary installation access. Set to false after controller installation.
  enable_controller_bootstrap = true

  controller_bootstrap_clusters = {
    for name, cluster in module.eks : name => cluster
    if local.enable_controller_bootstrap
  }
}

data "aws_iam_policy_document" "controller_installer_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = [module.runner_iam.role_arn]
    }
  }
}

resource "aws_iam_role" "controller_installer" {
  count = local.enable_controller_bootstrap ? 1 : 0

  name                 = "sentinel-controller-installer"
  assume_role_policy   = data.aws_iam_policy_document.controller_installer_trust.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "runner_assume_controller_installer" {
  count = local.enable_controller_bootstrap ? 1 : 0

  statement {
    effect    = "Allow"
    actions   = ["sts:AssumeRole"]
    resources = [aws_iam_role.controller_installer[0].arn]
  }
}

resource "aws_iam_role_policy" "runner_assume_controller_installer" {
  count = local.enable_controller_bootstrap ? 1 : 0

  name   = "sentinel-assume-controller-installer"
  role   = module.runner_iam.role_name
  policy = data.aws_iam_policy_document.runner_assume_controller_installer[0].json
}

resource "aws_eks_access_entry" "controller_installer" {
  for_each = local.controller_bootstrap_clusters

  cluster_name  = each.value.cluster_name
  principal_arn = aws_iam_role.controller_installer[0].arn
  type          = "STANDARD"
}

resource "aws_eks_access_policy_association" "controller_installer" {
  for_each = local.controller_bootstrap_clusters

  cluster_name  = each.value.cluster_name
  principal_arn = aws_eks_access_entry.controller_installer[each.key].principal_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"

  access_scope {
    type = "cluster"
  }
}