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
# Cloud Run (eu-west1) -> VM GPU api-catalog gRPC
# Autorise le VPC Connector serverless eu-west1 a joindre api-catalog-service.
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
  description = "Allow Cloud Run eu-west1 VPC Connector to reach api-catalog gRPC on VM GPU"

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
# Secret Manager
# Secrets dedies par service (<service>-<key>) + secrets plateforme partages
# (platform-<key>). Les VALEURS sont injectees hors Terraform via
# 'gcloud secrets versions add' (eviter d'avoir les secrets dans le state TF).
# -----------------------------------------------------------------------------
module "secret_manager" {
  source = "./modules/secret_manager"
  secrets = {
    # -------------------------------------------------------------------------
    # Secrets DEDIES account-service-backend
    # NB : 6/7 sont en realite des secrets PARTAGES -> migration retroactive
    # vers platform-* prevue ulterieurement (hors scope actuel).
    # Conserves tels quels pour l'instant (account-service-backend les consomme).
    # -------------------------------------------------------------------------
    "account-service-backend-mysql-pass"           = { service = "account-service-backend" }
    "account-service-backend-encryption-key"       = { service = "account-service-backend" }
    "account-service-backend-jwt-secret"           = { service = "account-service-backend" }
    "account-service-backend-fallback-pass"        = { service = "account-service-backend" }
    "account-service-backend-internal-admin-token" = { service = "account-service-backend" }
    "account-service-backend-catalog-admin-key"    = { service = "account-service-backend" }
    "account-service-backend-slack-webhook-url"    = { service = "account-service-backend" }

    # -------------------------------------------------------------------------
    # Secrets PLATEFORME partages (consommes par >=2 services).
    # Une entree = rotation atomique cross-services (1 valeur = 1 secret).
    # VALEURS injectees hors TF via 'gcloud secrets versions add' depuis .env.
    # -------------------------------------------------------------------------
    # Auth / plateforme
    "platform-jwt-secret"             = { service = "platform" }
    "platform-account-internal-token" = { service = "platform" }
    "platform-catalog-admin-key"      = { service = "platform" }
    "platform-gateway-admin-key"      = { service = "platform" }
    "platform-mcp-encryption-key"     = { service = "platform" }
    "platform-mcp-fallback-pass"      = { service = "platform" }
    # DB / cache / broker / graph
    "platform-gateway-mysql-pass"      = { service = "platform" }
    "platform-gateway-mysql-root-pass" = { service = "platform" }
    "platform-redis-secret"            = { service = "platform" }
    "platform-rabbitmq-url"            = { service = "platform" }
    "platform-neo4j-password"          = { service = "platform" }
    # Zilliz/Milvus : auth user+password (ZILLIZ_API_KEY=none dans .env, non utilise).
    "platform-zilliz-user"     = { service = "platform" }
    "platform-zilliz-password" = { service = "platform" }
    # LLM providers
    "platform-openai-api-key"     = { service = "platform" }
    "platform-gemini-api-key"     = { service = "platform" }
    "platform-deepseek-api-key"   = { service = "platform" }
    "platform-openrouter-api-key" = { service = "platform" }
    "platform-embedding-api-key"  = { service = "platform" }
    # API HelloPro
    "platform-hp-token"                  = { service = "platform" }
    "platform-hellopro-api-bearer-token" = { service = "platform" }
    # Notif
    "platform-slack-webhook-url" = { service = "platform" }
    # MCP gateway <-> backends (tokens de liaison partages par paire)
    "platform-mcp-ringover-admin-token"         = { service = "platform" }
    "platform-mcp-leexi-admin-token"            = { service = "platform" }
    "platform-mcp-templates-runner-admin-token" = { service = "platform" }
    "platform-zoho-gateway-token"               = { service = "platform" }
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
# Service Accounts CI/CD + Workload Identity Federation
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
# devops-infra-sa : Secret Manager admin
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
# devops-infra-sa : viewer projet (lectures .list/.get uniformes)
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
# devops-infra-sa : Cloud Run admin
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
# devops-infra-sa : compute security admin (gestion des regles firewall)
# Necessaire pour creer/manage les regles firewall GCP (compute.firewalls.*),
# ex. la regle d'acces Cloud Run eu-west1 -> api-catalog gRPC sur la VM GPU.
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

