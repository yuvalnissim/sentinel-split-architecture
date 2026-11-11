module "runner_iam" {
  source = "./modules/runner-iam"

  role_name = "sentinel-private-runner"
}