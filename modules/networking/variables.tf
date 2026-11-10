variable "name" {
  description = "Name of the network."
  type        = string
}

variable "vpc_cidr" {
  description = "IPv4 CIDR block for the VPC."
  type        = string
}

variable "private_subnets" {
  description = "Private subnets keyed by a stable logical name."
  type = map(object({
    cidr_block        = string
    availability_zone = string
  }))
}