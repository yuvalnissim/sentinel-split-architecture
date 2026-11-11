data "aws_iam_policy_document" "runner_describe_clusters" {
  statement {
    sid     = "DescribeSentinelClusters"
    effect  = "Allow"
    actions = ["eks:DescribeCluster"]

    resources = [
      for cluster in module.eks : cluster.cluster_arn
    ]
  }
}

resource "aws_iam_role_policy" "runner_describe_clusters" {
  name   = "sentinel-describe-clusters"
  role   = module.runner_iam.role_name
  policy = data.aws_iam_policy_document.runner_describe_clusters.json
}

resource "aws_eks_access_entry" "runner" {
  for_each = module.eks

  cluster_name  = each.value.cluster_name
  principal_arn = module.runner_iam.role_arn
  type          = "STANDARD"
}

resource "aws_eks_access_policy_association" "runner_view" {
  for_each = module.eks

  cluster_name  = each.value.cluster_name
  principal_arn = aws_eks_access_entry.runner[each.key].principal_arn

  policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy"

  access_scope {
    type = "cluster"
  }
}