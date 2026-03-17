# =============================================================================
# Module: Secret Manager
# Gestion centralisee des secrets via GCP Secret Manager
# Source: Extrait de infra-ci-cd/terraform/main.tf (lignes 98-121)
# =============================================================================

resource "google_secret_manager_secret" "secrets" {
  for_each  = var.secrets
  secret_id = each.key

  replication {
    auto {}
  }

  labels = merge(
    {
      managed_by = "terraform"
      service    = each.value.service
    },
    var.common_labels
  )
}
