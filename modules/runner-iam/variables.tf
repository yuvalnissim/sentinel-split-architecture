variable "role_name" {
  description = "IAM role and instance profile name for the private runner."
  type        = string

  validation {
    condition     = startswith(var.role_name, "sentinel-")
    error_message = "Runner IAM role names must start with sentinel-."
  }
}