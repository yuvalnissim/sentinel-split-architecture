module "runner" {
  source = "./modules/runner"

  name                  = "sentinel-private-runner"
  vpc_id                = module.network["gateway"].vpc_id
  subnet_id             = module.network["gateway"].private_subnet_ids["a"]
  instance_profile_name = module.runner_iam.instance_profile_name

  depends_on = [
    module.network,
    module.runner_iam,
  ]
}

output "runner" {
  description = "Private runner connection details."

  value = {
    instance_id       = module.runner.instance_id
    private_ip        = module.runner.private_ip
    security_group_id = module.runner.security_group_id
  }
}