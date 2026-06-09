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

  lifecycle {
    ignore_changes = [
      log_config,
    ]
  }
}

resource "google_compute_subnetwork" "proxy_only_subnet" {
  project       = var.project_id
  name          = "proxy-subnet"
  provider      = google-beta
  ip_cidr_range = var.proxy_subnet_prefix
  region        = "europe-west1"
  purpose       = "GLOBAL_MANAGED_PROXY"
  role          = "ACTIVE"
  network       = google_compute_network.vpc.id
}

#############################################
# Locals : agrège automatiquement les CIDR
#############################################
locals {
  # Toutes les plages des subnets (ew1 + ew4) du VPC
  vpc_subnet_cidrs = [for s in google_compute_subnetwork.subnets : s.ip_cidr_range]

  # Ranges GKE (pods & services) si tu veux joindre directement les Pods
  pods_svcs_cidrs = compact([
    var.cidr_range_pods,
    var.cidr_range_svcs
  ])

  internal_sources = concat(local.vpc_subnet_cidrs, local.pods_svcs_cidrs)
}

#############################################
# Firewall : autorise l’ingress intra-VPC
# (ICMP + TCP/UDP) depuis tes plages internes
#############################################
resource "google_compute_firewall" "allow-internal-all" {
  project   = var.project_id
  name      = "${var.name}-allow-internal-all"
  network   = google_compute_network.vpc.name
  direction = "INGRESS"
  priority  = 1000

  source_ranges = local.internal_sources

  allow { protocol = "icmp" }
  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }
  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }

  # Option: cible tous les VMs du réseau (pas de target_tags)
  # Si tu veux restreindre, mets: target_tags = ["dlvm","manager","gke-nodes"]
}

#############################################
# NAT pour europe-west4 : en prod
# si IP publique VM GPU non definie
#############################################
# Cloud Router + Cloud NAT pour europe-west4
# resource "google_compute_router" "nat_ew4" {
#   name    = "${var.name}-nat-ew4"
#   region  = "europe-west4"
#   network = google_compute_network.vpc.name
# }

# resource "google_compute_router_nat" "nat_ew4" {
#   name   = "${var.name}-nat-ew4"
#   region = "europe-west4"
#   router = google_compute_router.nat_ew4.name

#   nat_ip_allocate_option             = "AUTO_ONLY"
#   source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
# }
#############################################