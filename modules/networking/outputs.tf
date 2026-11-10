output "vpc_id" {
  description = "ID of the VPC."
  value       = aws_vpc.this.id
}

output "vpc_cidr" {
  description = "IPv4 CIDR block of the VPC."
  value       = aws_vpc.this.cidr_block
}

output "private_subnet_ids" {
  description = "Private subnet IDs keyed by logical name."
  value = {
    for name, subnet in aws_subnet.private : name => subnet.id
  }
}

output "private_route_table_ids" {
  description = "Private route table IDs keyed by logical subnet name."
  value = {
    for name, route_table in aws_route_table.private :
    name => route_table.id
  }
}

output "public_subnet_ids" {
  description = "Public subnet IDs keyed by logical name."
  value = {
    for name, subnet in aws_subnet.public : name => subnet.id
  }
}