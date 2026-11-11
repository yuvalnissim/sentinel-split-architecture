resource "aws_eks_access_policy_association" "runner_app_deploy" {
  for_each = module.eks

  cluster_name  = each.value.cluster_name
  principal_arn = aws_eks_access_entry.runner[each.key].principal_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy"

  access_scope {
    type       = "namespace"
    namespaces = ["default"]
  }
}