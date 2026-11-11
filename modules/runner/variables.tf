variable "name" {
  description = "Runner instance name."
  type        = string
}

variable "vpc_id" {
  description = "VPC hosting the runner."
  type        = string
}

variable "subnet_id" {
  description = "Private subnet hosting the runner."
  type        = string
}

variable "instance_profile_name" {
  description = "IAM instance profile attached to the runner."
  type        = string
}