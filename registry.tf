module "registry" {
  for_each = toset(["backend", "gateway"])

  source = "./modules/registry"

  name = "sentinel/${each.key}"

  # Lab environment: remove images together with the repository during teardown.
  force_delete = true
}

output "repositories" {
  description = "Private container repository URLs."

  value = {
    for name, repository in module.registry :
    name => repository.repository_url
  }
}