output "role_arn" {
  description = "Runner IAM role ARN."
  value       = aws_iam_role.runner.arn
}

output "role_name" {
  description = "Runner IAM role name."
  value       = aws_iam_role.runner.name
}

output "instance_profile_name" {
  description = "Instance profile attached to the runner EC2 instance."
  value       = aws_iam_instance_profile.runner.name
}