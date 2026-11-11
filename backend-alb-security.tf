resource "aws_security_group" "backend_alb" {
  name        = "sentinel-backend-alb"
  description = "Private backend ALB accessible from gateway cluster nodes"
  vpc_id      = module.network["backend"].vpc_id

  tags = {
    Name = "sentinel-backend-alb"
  }
}

resource "aws_vpc_security_group_ingress_rule" "backend_alb_from_gateway" {
  security_group_id = aws_security_group.backend_alb.id

  description = "HTTP from gateway cluster nodes and pods"

  referenced_security_group_id = module.eks["gateway"].cluster_security_group_id

  ip_protocol = "tcp"
  from_port   = 80
  to_port     = 80
}

resource "aws_vpc_security_group_egress_rule" "backend_alb_to_backend" {
  security_group_id = aws_security_group.backend_alb.id

  description = "Application and health check traffic to backend pods"

  referenced_security_group_id = module.eks["backend"].cluster_security_group_id

  ip_protocol = "tcp"
  from_port   = 8080
  to_port     = 8080
}

output "backend_alb_security_group_id" {
  description = "Security group for the private backend ALB."
  value       = aws_security_group.backend_alb.id
}