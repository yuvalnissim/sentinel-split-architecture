variable "aws_region" {
  description = "AWS Region used by the Sentinel environment."
  type        = string
  default     = "eu-north-1"

  validation {
    condition     = var.aws_region == "eu-north-1"
    error_message = "This proof of concept is restricted to eu-north-1."
  }
}

variable "aws_account_id" {
  description = "AWS account allowed to host the Sentinel environment."
  type        = string
  default     = "485378272094"

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "The AWS account ID must contain exactly 12 digits."
  }
}

variable "enable_cni_bootstrap" {
  description = "Temporarily grant node roles CNI permissions during initial cluster creation. Disable after verifying CNI Pod Identity."
  type        = bool
  default     = false
}

variable "enable_controller_bootstrap" {
  description = "Temporarily allow the private runner to assume the controller installer role."
  type        = bool
  default     = false
}
