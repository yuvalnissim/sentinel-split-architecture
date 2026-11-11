resource "aws_eks_addon" "pod_identity_agent" {
  cluster_name  = aws_eks_cluster.this.name
  addon_name    = "eks-pod-identity-agent"
  addon_version = "v1.4.1-eksbuild.3"

  depends_on = [
    aws_eks_node_group.this,
  ]
}