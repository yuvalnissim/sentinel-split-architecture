variable "gateway_vpc_id" {
  description = "Gateway VPC ID."
  type        = string
}

variable "backend_vpc_id" {
  description = "Backend VPC ID."
  type        = string
}

variable "gateway_cidr" {
  description = "Gateway VPC IPv4 CIDR."
  type        = string
}

variable "backend_cidr" {
  description = "Backend VPC IPv4 CIDR."
  type        = string
}

variable "gateway_route_table_ids" {
  description = "Gateway private route table IDs."
  type        = map(string)
}

variable "backend_route_table_ids" {
  description = "Backend private route table IDs."
  type        = map(string)
}