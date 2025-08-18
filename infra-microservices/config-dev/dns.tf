module "dns" {
  source     = "../modules/dns"
  project_id     = var.project_id
  zone_name        = var.zone_name
  dns_name    = var.dns_name

  network = module.vpc.vpc_id

}














