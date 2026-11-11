output "repository_arn" {
  description = "ECR repository ARN."
  value       = aws_ecr_repository.this.arn
}

output "repository_url" {
  description = "ECR repository URL for image push and pull."
  value       = aws_ecr_repository.this.repository_url
}