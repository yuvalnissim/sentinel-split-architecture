module "eks" {
  for_each = local.networks

  source = "./modules/eks"

  cluster_name       = "eks-${each.key}"
  kubernetes_version = "1.37"

  private_subnet_ids = values(
    module.network[each.key].private_subnet_ids
  )

  runner_security_group_id = module.runner.security_group_id

  depends_on = [
    module.peering,
  ]
}

output "clusters" {
  description = "Sentinel EKS cluster connection details."

  value = {
    for name, cluster in module.eks : name => {
      name     = cluster.cluster_name
      endpoint = cluster.endpoint
    }
  }
}