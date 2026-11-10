locals {
  networks = {
    gateway = {
      name     = "vpc-gateway"
      vpc_cidr = "10.30.0.0/16"

      private_subnets = {
        a = {
          cidr_block        = "10.30.11.0/24"
          availability_zone = "eu-north-1a"
        }
        b = {
          cidr_block        = "10.30.12.0/24"
          availability_zone = "eu-north-1b"
        }
      }
    }

    backend = {
      name     = "vpc-backend"
      vpc_cidr = "10.40.0.0/16"

      private_subnets = {
        a = {
          cidr_block        = "10.40.11.0/24"
          availability_zone = "eu-north-1a"
        }
        b = {
          cidr_block        = "10.40.12.0/24"
          availability_zone = "eu-north-1b"
        }
      }
    }
  }
}

module "network" {
  for_each = local.networks

  source = "./modules/networking"

  name            = each.value.name
  vpc_cidr        = each.value.vpc_cidr
  private_subnets = each.value.private_subnets
}

output "networks" {
  description = "Network identifiers for both Sentinel domains."
  value = {
    for name, network in module.network : name => {
      vpc_id             = network.vpc_id
      private_subnet_ids = network.private_subnet_ids
    }
  }
}