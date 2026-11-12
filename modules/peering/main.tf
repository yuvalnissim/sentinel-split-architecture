terraform {
  required_version = ">= 1.16.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

resource "aws_vpc_peering_connection" "this" {
  vpc_id      = var.gateway_vpc_id
  peer_vpc_id = var.backend_vpc_id
  auto_accept = true

  tags = {
    Name = "sentinel-gateway-backend"
  }
}

resource "aws_route" "gateway_to_backend" {
  for_each = var.gateway_route_table_ids

  route_table_id            = each.value
  destination_cidr_block    = var.backend_cidr
  vpc_peering_connection_id = aws_vpc_peering_connection.this.id
}

resource "aws_route" "backend_to_gateway" {
  for_each = var.backend_route_table_ids

  route_table_id            = each.value
  destination_cidr_block    = var.gateway_cidr
  vpc_peering_connection_id = aws_vpc_peering_connection.this.id
}