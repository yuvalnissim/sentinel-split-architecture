output "instance_id" {
  description = "Private runner EC2 instance ID."
  value       = aws_instance.runner.id
}

output "private_ip" {
  description = "Private runner IP address."
  value       = aws_instance.runner.private_ip
}

output "security_group_id" {
  description = "Runner security group ID."
  value       = aws_security_group.runner.id
}