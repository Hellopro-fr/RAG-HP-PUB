resource "google_compute_address" "adress" {
  name         = "${var.name}-adress"
  subnetwork   = var.subnetwork
  address_type = "INTERNAL"
  address      = var.ip_milvus
  region       = var.region
  project      = var.project_id
}

resource "google_compute_global_forwarding_rule" "fw" {
  project               = var.project_id
  name                  = "${var.name}-ilb-forwarding-rule"
  provider              = google-beta
  ip_protocol           = "TCP"
  load_balancing_scheme = "INTERNAL_MANAGED"
  port_range            = var.port
  target                = google_compute_target_http_proxy.http_proxy.id
  network               = var.network
  subnetwork            = var.subnetwork
  ip_address            = google_compute_address.adress.address
}

resource "google_compute_target_http_proxy" "http_proxy" {
  project  = var.project_id
  provider = google-beta
  name     = "${var.name}-ilb-http-proxy"
  url_map  = google_compute_url_map.urlmap.id
}

# backend service
resource "google_compute_backend_service" "backend_service" {
  provider              = google-beta
  project               = var.project_id
  name                  = "${var.name}-ilb-backend"
  protocol              = "HTTP"
  load_balancing_scheme = "INTERNAL_MANAGED"
  #  health_checks         = [google_compute_health_check.health_check.id]
  backend {
    group = var.group
  }
}

resource "google_compute_url_map" "urlmap" {
  name            = "${var.name}-ilb-urlmap"
  default_service = google_compute_backend_service.backend_service.id
}

#resource "google_compute_health_check" "health_check" {
#  project     = var.project_id
#  provider           = google-beta
#  name               = "${var.name}-health-check"
#  tcp_health_check {
#    port = var.port
#  }
#}