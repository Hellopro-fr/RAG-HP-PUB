# =============================================================================
# providers.tf - Infrastructure Microservices RAG HelloPro
# =============================================================================

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    # Pin sur ~> 6.0 (stable) pour eviter les bugs des releases trop recentes
    # sur Windows (timeout plugin gRPC observe avec v7.35.0).
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}
