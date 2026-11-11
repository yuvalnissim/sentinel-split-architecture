variable "cluster_name" {
  description = "EKS cluster name and prefix for its IAM role."
  type        = string

  validation {
    condition     = startswith(var.cluster_name, "eks-")
    error_message = "Cluster names must start with eks-."
  }
}

variable "kubernetes_version" {
  description = "Kubernetes version for the cluster."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnets in at least two Availability Zones."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "Provide at least two private subnets."
  }
}

variable "runner_security_group_id" {
  description = "Security group allowed to reach the private Kubernetes API."
  type        = string
}