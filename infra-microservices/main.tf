# =============================================================================
# main.tf - Infrastructure Microservices RAG HelloPro
# Structure centralisée - Un seul code, plusieurs environnements via tfvars
# Usage: terraform plan -var-file=environments/dev/terraform.tfvars
# =============================================================================

# -----------------------------------------------------------------------------
# VPC & Networking
# -----------------------------------------------------------------------------
module "vpc" {
  source              = "./modules/vpc"
  name                = "hellopro-${var.environment}-vpc"
  project_id          = var.project_id
  subnetworks         = var.subnetworks
  proxy_subnet_prefix = var.proxy_subnet_prefix
  cidr_range_master   = var.cidr_range_master
  cidr_range_pods     = var.cidr_range_pods
  cidr_range_svcs     = var.cidr_range_svcs
}

module "access_connector" {
  source                                 = "./modules/access_connector"
  network                                = module.vpc.vpc_name
  region                                 = var.region
  ip_cidr_range_vpc_connector_serverless = var.ip_cidr_range_vpc_connector_serverless
  project_id                             = var.project_id
}

# -----------------------------------------------------------------------------
# Firewall Rules
# -----------------------------------------------------------------------------
resource "google_compute_firewall" "allow_ssh" {
  name        = "allow-ssh"
  network     = module.vpc.vpc_name
  direction   = "INGRESS"
  priority    = 1000
  description = "Remediated: SSH restricted to IAP."

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  target_tags   = var.node_ntwk_tag
  source_ranges = ["35.235.240.0/20"]

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}

resource "google_compute_firewall" "allow-intra-lan" {
  name        = "allow-intra-lan"
  network     = module.vpc.vpc_name
  description = "Remediated: Restricted Internal Only"

  allow {
    protocol = "all"
  }

  source_ranges = [
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "10.11.0.0/20"
  ]

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}

# -----------------------------------------------------------------------------
# GKE Cluster
# -----------------------------------------------------------------------------
module "gke_cluster" {
  source                       = "./modules/gke_cluster"
  project_id                   = var.project_id
  name                         = var.name
  zone                         = var.zone
  network                      = module.vpc.vpc_name
  subnetwork                   = module.vpc.subnetworks["hellopro-subnet-${var.environment}"].self_link
  gke_cluster_nb_nodes         = var.gke_cluster_nb_nodes
  gke_cluster_nb_nodes_final   = var.gke_cluster_nb_nodes_final
  gke_type_machine             = var.gke_type_machine
  node_ntwk_tag                = var.node_ntwk_tag
  cidr_range_pods              = var.cidr_range_pods
  cidr_range_svcs              = var.cidr_range_svcs
  cidr_range_master            = var.cidr_range_master
  master_authorized_networks_0 = var.master_authorized_networks_0
}

# -----------------------------------------------------------------------------
# Compute Instances
# -----------------------------------------------------------------------------
module "vm" {
  source     = "./modules/compute_instance"
  name       = "manager-vm-${var.environment}"
  project_id = var.project_id
  zone       = var.zone
  network    = module.vpc.vpc_name
  subnetwork = module.vpc.subnetworks["hellopro-subnet-${var.environment}"].self_link
  tags       = ["http-server", "ssh"]
}

# -----------------------------------------------------------------------------
# DNS
# -----------------------------------------------------------------------------
module "dns" {
  source     = "./modules/dns"
  project_id = var.project_id
  zone_name  = var.zone_name
  dns_name   = var.dns_name
  network    = module.vpc.vpc_id
}

resource "google_dns_record_set" "ip_scraping" {
  project      = var.project_id
  name         = "scraping.${module.dns.dns_zone}"
  type         = "A"
  ttl          = 300
  managed_zone = module.dns.dns_name
  rrdatas      = [var.ip_scraping]
}

resource "google_dns_record_set" "ip_rabbitmq" {
  project      = var.project_id
  name         = "rabbitmq.${module.dns.dns_zone}"
  type         = "A"
  ttl          = 300
  managed_zone = module.dns.dns_name
  rrdatas      = [var.ip_rabbitmq]
}

resource "google_dns_record_set" "ip_etl_dataflow" {
  project      = var.project_id
  name         = "etl_dataflow.${module.dns.dns_zone}"
  type         = "A"
  ttl          = 300
  managed_zone = module.dns.dns_name
  rrdatas      = [var.ip_etl_dataflow]
}

resource "google_dns_record_set" "ip_chunkind_llm" {
  project      = var.project_id
  name         = "llm.${module.dns.dns_zone}"
  type         = "A"
  ttl          = 300
  managed_zone = module.dns.dns_name
  rrdatas      = [var.ip_chunkind_llm]
}

resource "google_dns_record_set" "ip_embedding" {
  project      = var.project_id
  name         = "embedding.${module.dns.dns_zone}"
  type         = "A"
  ttl          = 300
  managed_zone = module.dns.dns_name
  rrdatas      = [var.ip_embedding]
}

resource "google_dns_record_set" "ip_milvus" {
  project      = var.project_id
  name         = "milvus.${module.dns.dns_zone}"
  type         = "A"
  ttl          = 300
  managed_zone = module.dns.dns_name
  rrdatas      = [var.ip_milvus]
}

resource "google_dns_record_set" "ip_redis" {
  project      = var.project_id
  name         = "redis.${module.dns.dns_zone}"
  type         = "A"
  ttl          = 300
  managed_zone = module.dns.dns_name
  rrdatas      = [var.ip_redis]
}

resource "google_dns_record_set" "ip_matching_api" {
  project      = var.project_id
  name         = "matching_api.${module.dns.dns_zone}"
  type         = "A"
  ttl          = 300
  managed_zone = module.dns.dns_name
  rrdatas      = [var.ip_matching_api]
}

# -----------------------------------------------------------------------------
# Artifact Registry
# -----------------------------------------------------------------------------
module "artifact_registry" {
  source        = "./modules/artifact_registry"
  repository_id = var.repository_id
  description   = "Docker registry for my project"
}

# -----------------------------------------------------------------------------
# Internal Load Balancer
# -----------------------------------------------------------------------------
module "ilb" {
  source     = "./modules/internal_lb"
  project_id = var.project_id
  name       = "cleaner-etl-${var.environment}-ilb"
  ip_milvus  = var.ip_etl_dataflow
  region     = var.region
  network    = module.vpc.vpc_name
  subnetwork = module.vpc.subnetworks["hellopro-subnet-${var.environment}"].self_link
  group      = "projects/${var.project_id}/regions/${var.region}/networkEndpointGroups/cleaner-etl-${var.environment}-neg"
  port       = "80"
}

# -----------------------------------------------------------------------------
# Cloud NAT (Phase 3 - Securisation)
# Permet aux VMs sans IP publique d'acceder a Internet
# -----------------------------------------------------------------------------
# module "cloud_nat" {
#   source      = "./modules/cloud_nat"
#   project_id  = var.project_id
#   region      = var.region
#   network     = module.vpc.vpc_name
#   environment = var.environment
# }

# -----------------------------------------------------------------------------
# Secret Manager (Phase 3 - Gestion des secrets)
# Source: Migre depuis infra-ci-cd/terraform/main.tf
# -----------------------------------------------------------------------------
# module "secret_manager" {
#   source = "./modules/secret_manager"
#   secrets = {
#     "neo4j-password" = {
#       service = "database"
#     }
#     "external-api-keys" = {
#       service = "api"
#     }
#     "rabbitmq-credentials" = {
#       service = "messaging"
#     }
#     "redis-password" = {
#       service = "cache"
#     }
#     "jwt-signing-key" = {
#       service = "api-gateway"
#     }
#     "milvus-credentials" = {
#       service = "vector-database"
#     }
#   }
#   common_labels = {
#     environment = var.environment
#     project     = "rag-hp"
#   }
# }

# -----------------------------------------------------------------------------
# Service Accounts CI/CD (Phase 3/4)
# Source: Migre depuis infra-ci-cd/terraform/main.tf
# -----------------------------------------------------------------------------
# module "service_accounts" {
#   source     = "./modules/service_accounts"
#   project_id = var.project_id
#   dedicated_service_accounts = {
#     "milvus-reader" = {
#       display_name = "Milvus Reader SA"
#       description  = "Service account pour les services lisant Milvus"
#       roles        = ["roles/storage.objectViewer"]
#     }
#     "rabbitmq-consumer" = {
#       display_name = "RabbitMQ Consumer SA"
#       description  = "Service account pour les processor services"
#       roles        = ["roles/logging.logWriter"]
#     }
#     "gcs-backup-writer" = {
#       display_name = "GCS Backup Writer SA"
#       description  = "Service account pour les jobs de backup"
#       roles        = ["roles/storage.objectAdmin"]
#     }
#   }
# }

# -----------------------------------------------------------------------------
# Monitoring & Alerting (Phase 3/5)
# Source: Migre depuis infra-ci-cd/terraform/main.tf
# NOTE: Decommenter quand alert_email et billing_account_id sont configures
# -----------------------------------------------------------------------------
# module "monitoring" {
#   source             = "./modules/monitoring"
#   project_id         = var.project_id
#   environment        = var.environment
#   alert_email        = var.alert_email
#   monthly_budget     = var.monthly_budget
#   billing_account_id = var.billing_account_id
# }

# -----------------------------------------------------------------------------
# Data Sources (Non utilisés - commentés pour éviter erreurs)
# -----------------------------------------------------------------------------
# data "google_compute_image" "dlvm_pytorch" {
#   project = "deeplearning-platform-release"
#   family  = var.dlvm_family
#   # NOTE: Si réactivé, vérifiez la famille disponible avec:
#   # gcloud compute images list --project=deeplearning-platform-release | grep pytorch
# }

