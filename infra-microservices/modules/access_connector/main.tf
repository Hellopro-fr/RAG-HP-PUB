resource "google_vpc_access_connector" "access_connector" {
  project        = var.project_id
  name           = "vpc-access-connector"
  ip_cidr_range  = var.ip_cidr_range_vpc_connector_serverless
  machine_type   = "e2-micro"
  max_throughput = "1000"
  min_throughput = "400"
  region         = var.region
  network        = var.network

}
