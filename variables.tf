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