terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

data "aws_ssm_parameter" "amazon_linux" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_security_group" "runner" {
  name_prefix = "${var.name}-"
  description = "Private runner with no inbound access"
  vpc_id      = var.vpc_id

  tags = {
    Name = "${var.name}-sg"
  }
}

resource "aws_vpc_security_group_egress_rule" "https" {
  security_group_id = aws_security_group.runner.id

  description = "HTTPS access to GitHub and AWS APIs"
  cidr_ipv4   = "0.0.0.0/0"
  ip_protocol = "tcp"
  from_port   = 443
  to_port     = 443
}

resource "aws_instance" "runner" {
  ami                         = nonsensitive(data.aws_ssm_parameter.amazon_linux.value)
  instance_type               = "t3.micro"
  subnet_id                   = var.subnet_id
  associate_public_ip_address = false
  iam_instance_profile        = var.instance_profile_name

  vpc_security_group_ids = [
    aws_security_group.runner.id,
  ]

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 12
    encrypted             = true
    delete_on_termination = true
  }

  credit_specification {
    cpu_credits = "standard"
  }

  tags = {
    Name = var.name
  }

  depends_on = [
    aws_vpc_security_group_egress_rule.https,
  ]
}