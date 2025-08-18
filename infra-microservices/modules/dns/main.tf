resource "google_dns_managed_zone" "private_zone" {
  project     = var.project_id
  name        = var.zone_name
  dns_name    = var.dns_name
  description = " private DNS zone"

  visibility = "private"

  private_visibility_config {
    networks {
      network_url = var.network
    }
  }
}