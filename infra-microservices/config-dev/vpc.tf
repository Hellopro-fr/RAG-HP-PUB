module "vpc" {
  source     = "../modules/vpc"
  name       = "hellopro-dev-vpc"
  project_id = var.project_id
  subnetworks = var.subnetworks
  proxy_subnet_prefix = var.proxy_subnet_prefix
}
