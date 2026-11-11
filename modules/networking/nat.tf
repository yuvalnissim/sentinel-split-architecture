resource "aws_eip" "nat" {
  domain = "vpc"

  tags = {
    Name = "${var.name}-nat-ip"
  }
}

resource "aws_nat_gateway" "this" {
  allocation_id     = aws_eip.nat.id
  subnet_id         = aws_subnet.public["a"].id
  connectivity_type = "public"

  depends_on = [
    aws_internet_gateway.this,
    aws_route.public_internet,
    aws_route_table_association.public,
  ]

  tags = {
    Name = "${var.name}-nat"
  }
}

resource "aws_route" "private_internet" {
  for_each = var.private_subnets

  route_table_id         = aws_route_table.private[each.key].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this.id
}