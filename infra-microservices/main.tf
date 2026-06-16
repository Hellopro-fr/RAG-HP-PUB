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
# F-HP-NGINX-001 / T001-S003-000 - Cloud Run -> VM GPU api-catalog gRPC
# Cree manuellement le 2026-06-15 pour debloquer la route /admin/api du POC #1.
# Importer dans le state via :
#   terraform import google_compute_firewall.allow_cr_eu_to_vm_gpu_api_catalog \
#     projects/hellopro-rag-project/global/firewalls/allow-cr-eu-to-vm-gpu-api-catalog
# Source : VPC Connector eu-west1 (range 10.0.2.0/28).
# Target : SA de la VM GPU vm-gpu-runtime@ (cible precise sans tags).
# Ports : 19100/19101 = mapping hote dedie pour api-catalog-service
#         (9100 hote = node_exporter, conserver ; conteneur ecoute 9100/9101 en interne Docker).
# -----------------------------------------------------------------------------
resource "google_compute_firewall" "allow_cr_eu_to_vm_gpu_api_catalog" {
  name        = "allow-cr-eu-to-vm-gpu-api-catalog"
  network     = module.vpc.vpc_name
  direction   = "INGRESS"
  priority    = 1000
  description = "POC#1 Sprint S003: Allow Cloud Run eu-west1 VPC Connector to reach api-catalog gRPC on VM GPU (T001-S003-000)"

  allow {
    protocol = "tcp"
    ports    = ["19100", "19101"]
  }

  source_ranges = ["10.0.2.0/28"]
  target_service_accounts = [
    "vm-gpu-runtime@${var.project_id}.iam.gserviceaccount.com"
  ]
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
# Secret Manager (Ticket 001-INFRA-GCP-ARCHI Sprint 002)
# Active uniquement avec les secrets POC #1 (account-service-backend).
# Les autres secrets seront ajoutes service par service lors de leur migration.
# Les VALEURS sont injectees hors Terraform via gcloud secrets versions add
# (eviter d'avoir les secrets dans le state Terraform).
# -----------------------------------------------------------------------------
module "secret_manager" {
  source = "./modules/secret_manager"
  # Perimetre POC #1 (account-service-backend) - revision Sprint 002 apres lecture
  # du .env reel et docker-compose.yml lignes 2522-2570.
  # Mapping :
  #   mysql-pass            <- GATEWAY_MYSQL_PASS (partage api-gateway)
  #   encryption-key        <- ACCOUNT_ENCRYPTION_KEY (chiffrement donnees users)
  #   jwt-secret            <- JWT_SECRET (partage plateforme)
  #   fallback-pass         <- MCP_FALLBACK_PASS (break-glass)
  #   internal-admin-token  <- ACCOUNT_INTERNAL_TOKEN (token interne MCP)
  #   catalog-admin-key     <- CATALOG_ADMIN_KEY (API Catalog)
  #   slack-webhook-url     <- SLACK_WEBHOOK_URL (URL contient le token)
  secrets = {
    "account-service-backend-mysql-pass"           = { service = "account-service-backend" }
    "account-service-backend-encryption-key"       = { service = "account-service-backend" }
    "account-service-backend-jwt-secret"           = { service = "account-service-backend" }
    "account-service-backend-fallback-pass"        = { service = "account-service-backend" }
    "account-service-backend-internal-admin-token" = { service = "account-service-backend" }
    "account-service-backend-catalog-admin-key"    = { service = "account-service-backend" }
    "account-service-backend-slack-webhook-url"    = { service = "account-service-backend" }
  }
  cloudrun_sa_email = module.service_accounts.cloudrun_sa_email
  common_labels = {
    environment = var.environment
    project     = "rag-hp"
    managed-by  = "terraform"
    ticket      = "001-infra-gcp-archi"
  }
}

# -----------------------------------------------------------------------------
# Service Accounts CI/CD + Workload Identity Federation (Sprint 002 Action 2.2)
# Cree :
#   - cloud-build-deployer (CI/CD legacy Cloud Build)
#   - cloudrun-services (SA runtime des services Cloud Run)
#   - github-deployer (CI/CD GitHub Actions via WIF, plus de cle JSON)
#   - WIF pool + provider OIDC GitHub (filtre par github_org + github_repo)
# -----------------------------------------------------------------------------
module "service_accounts" {
  source      = "./modules/service_accounts"
  project_id  = var.project_id
  github_org  = var.github_org
  github_repo = var.github_repo
}

# -----------------------------------------------------------------------------
# IAM hors-module : bindings sur SAs existants geres manuellement
# F-HP-IAM-001 remediation - Sprint 002 (2026-06-09)
# Le SA devops-infra-sa (cree hors TF) doit pouvoir gerer les versions Secret
# Manager pour eviter le contournement via compte humain CTO lors des pushes
# de valeurs (audit + gouvernance + autonomie equipe).
# -----------------------------------------------------------------------------
resource "google_project_iam_member" "devops_infra_sa_secretmanager_admin" {
  project = var.project_id
  role    = "roles/secretmanager.admin"
  member  = "serviceAccount:devops-infra-sa@${var.project_id}.iam.gserviceaccount.com"
}

# -----------------------------------------------------------------------------
# F-HP-IAM-002 remediation - Sprint 002 (2026-06-09)
# Pattern recurrent : devops-infra-sa peut creer/destruire des ressources mais
# n'a pas les .list/.get sur les divers services GCP (vpcaccess, dns, compute,
# run, etc.). Ajout de roles/viewer projet pour couvrir TOUTES les lectures
# de maniere uniforme - evite le yo-yo permission denied a chaque exploration.
# Coherent avec son scope d'admin infra : il peut deja tout creer/destruire,
# autoriser la lecture est logique. Audit Cloud Logging trace toutes les
# lectures => visibilite conservee.
# -----------------------------------------------------------------------------
resource "google_project_iam_member" "devops_infra_sa_viewer" {
  project = var.project_id
  role    = "roles/viewer"
  member  = "serviceAccount:devops-infra-sa@${var.project_id}.iam.gserviceaccount.com"
}

# -----------------------------------------------------------------------------
# F-HP-IAM-003 remediation - Sprint 002 (2026-06-10)
# devops-infra-sa doit pouvoir manage Cloud Run y compris setIamPolicy
# (allUsers binding via --allow-unauthenticated). Sans cela, un deploy CR
# avec allow_unauthenticated=true rend le service inaccessible (403).
# -----------------------------------------------------------------------------
resource "google_project_iam_member" "devops_infra_sa_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:devops-infra-sa@${var.project_id}.iam.gserviceaccount.com"
}

# -----------------------------------------------------------------------------
# F-HP-IAM-004 remediation - Sprint 003 (2026-06-15)
# devops-infra-sa doit pouvoir creer/manage les regles firewall GCP (compute.firewalls.*).
# Decouvert lors de la creation de allow-cr-eu-to-vm-gpu-api-catalog pour debloquer
# l'appel gRPC CR -> VM GPU api-catalog-service (POC #1 route /admin/api).
# Importer dans le state via :
#   terraform import google_project_iam_member.devops_infra_sa_compute_security_admin \
#     "hellopro-rag-project roles/compute.securityAdmin serviceAccount:devops-infra-sa@hellopro-rag-project.iam.gserviceaccount.com"
# -----------------------------------------------------------------------------
resource "google_project_iam_member" "devops_infra_sa_compute_security_admin" {
  project = var.project_id
  role    = "roles/compute.securityAdmin"
  member  = "serviceAccount:devops-infra-sa@${var.project_id}.iam.gserviceaccount.com"
}

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

