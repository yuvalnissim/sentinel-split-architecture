variable "name" {
  description = "Private ECR repository name."
  type        = string
}

variable "force_delete" {
  description = "Allow repository deletion even when it contains images."
  type        = bool
  default     = false
}