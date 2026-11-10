module "peering" {
  source = "./modules/peering"

  gateway_vpc_id = module.network["gateway"].vpc_id
  backend_vpc_id = module.network["backend"].vpc_id

  gateway_cidr = module.network["gateway"].vpc_cidr
  backend_cidr = module.network["backend"].vpc_cidr

  gateway_route_table_ids = module.network["gateway"].private_route_table_ids
  backend_route_table_ids = module.network["backend"].private_route_table_ids
}

output "vpc_peering_connection_id" {
  description = "Private connection between the Sentinel VPCs."
  value       = module.peering.connection_id
}