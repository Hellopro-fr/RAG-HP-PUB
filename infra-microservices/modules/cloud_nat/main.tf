# =============================================================================
# Module: Cloud NAT
# Permet aux VMs et pods sans IP publique d'acceder a Internet
# Prerequis pour retirer les IPs publiques des VMs GPU
# =============================================================================

resource "google_compute_router" "router" {
  name    = "nat-router-${var.environment}"
  project = var.project_id
  region  = var.region
  network = var.network
}

resource "google_compute_router_nat" "nat" {
  name                               = "cloud-nat-${var.environment}"
  project                            = var.project_id
  router                             = google_compute_router.router.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}
