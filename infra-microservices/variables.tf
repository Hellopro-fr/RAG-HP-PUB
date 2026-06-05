# =============================================================================
# Environment identifier
# =============================================================================
variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "project_id" {}
variable "zone" {}
variable "region" {}
variable "subnetwork" {}
variable "subnetworks" {
  description = "List of subnetworks"
  type = list(object({
    name          = string
    ip_cidr_range = string
    region        = string
  }))
}
variable "repository_id" {}


variable "description" {
  description = "Description du repository"
  type        = string
  default     = ""
}

variable "zone_name" {}
variable "dns_name" {}
# variable dns_name_prod {}
variable "ip_scraping" {}
variable "ip_rabbitmq" {}
variable "ip_etl_dataflow" {}
variable "ip_chunkind_llm" {}
variable "ip_embedding" {}
variable "ip_milvus" {}
variable "ip_redis" {}
variable "ip_matching_api" {}
variable "name" {}
variable "gke_cluster_nb_nodes" {}
variable "gke_cluster_nb_nodes_final" {}
variable "gke_type_machine" {}
variable "node_ntwk_tag" {

  type    = list(any)
  default = []
}
variable "cidr_range_pods" {}
variable "cidr_range_svcs" {}
variable "cidr_range_master" {}
variable "master_authorized_networks_0" {}
variable "port" {}
variable "group" {}
variable "proxy_subnet_prefix" {}
variable "ip_cidr_range_vpc_connector_serverless" {}


variable "mig_name" {
  type        = string
  description = "Managed Instance Group name"
}

variable "machine_type" {
  type    = string
  default = "e2-standard-4"
}

variable "min_size" {
  type    = number
  default = 1
}

variable "max_size" {
  type    = number
  default = 3
}

variable "disk_size_gb" {
  type    = number
  default = 50
}

variable "dlvm_family" {
  type    = string
  default = "pytorch-2-4-cu124-debian-11"
  # Liste des familles disponibles:
  # gcloud compute images list --project=deeplearning-platform-release --filter="family:pytorch" --format="value(family)" | sort -u
}


variable "machine_type_embedding" {
  description = "Machine type for the VM"
  type        = string
  default     = "e2-standard-4"

}

variable "image" {
  description = "Boot disk image"
  type        = string
  default     = "debian-cloud/debian-12"
}

variable "gpu_count" {
  description = "Nombre de GPU à attacher (0 pour désactiver)"
  type        = number
  default     = 0
}

variable "gpu_type" {
  description = "Type d'accélérateur, ex: nvidia-l4, nvidia-tesla-t4, nvidia-tesla-a100, nvidia-a100-80gb"
  type        = string
  default     = null
}

variable "install_gpu_startup_script" {
  description = "Installe le driver/CUDA au boot (si tu n'utilises pas une image DLVM)"
  type        = bool
  default     = false
}

# variable "subnetwork_self_link" {
#   description = "Self link du subnet (même VPC) dans la région du MIG (europe-west4)."
#   type        = string
# }

# =============================================================================
# Workload Identity Federation - GitHub Actions
# Ticket 001-INFRA-GCP-ARCHI Sprint 002 Action 2.2
# Variables consommees par module.service_accounts pour configurer WIF
# =============================================================================

variable "github_org" {
  description = "Organisation GitHub autorisee a utiliser WIF (ex: HelloPro). Filtre attribute_condition au niveau du WIF Provider."
  type        = string
}

variable "github_repo" {
  description = "Repo GitHub complet au format 'org/repo' (ex: HelloPro/RAG-HP-PUB). Limite l'impersonation du SA github-deployer aux workflows de ce repo uniquement."
  type        = string
}
