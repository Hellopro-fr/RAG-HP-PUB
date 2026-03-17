# =============================================================================
# backend.tf - Infrastructure Microservices RAG HelloPro
# Remote state configuration - uses -backend-config for environment prefix
#
# Usage:
#   terraform init -backend-config="prefix=dev/state" -reconfigure
#   terraform init -backend-config="prefix=prod/state" -reconfigure
# =============================================================================

terraform {
  backend "gcs" {
    bucket = "hellopro-terraform-state"
    # prefix is set via -backend-config flag per environment
  }
}
