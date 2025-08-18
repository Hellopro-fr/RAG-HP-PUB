resource "google_compute_network" "vpc" {
  name                    = var.name
  auto_create_subnetworks = false
  project                 = var.project_id
}

resource "google_compute_subnetwork" "subnets" {
  for_each = { for subnet in var.subnetworks : subnet.name => subnet }

  name          = each.value.name
  ip_cidr_range = each.value.ip_cidr_range
  region        = each.value.region
  network       = google_compute_network.vpc.id
  project       = var.project_id
}

resource "google_compute_subnetwork" "proxy_only_subnet" {
  project     = var.project_id
  name          = "proxy-subnet"
  provider      = google-beta
  ip_cidr_range = var.proxy_subnet_prefix
  region        = "europe-west1"
  purpose       = "GLOBAL_MANAGED_PROXY"
  role          = "ACTIVE"
  network       = google_compute_network.vpc.id
}