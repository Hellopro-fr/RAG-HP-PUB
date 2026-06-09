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

# IAM granulaire : Cloud Run SA peut lire chaque secret (least privilege).
# Pas de binding au niveau projet → blast radius limite au perimetre de ce module.
resource "google_secret_manager_secret_iam_member" "cloudrun_accessor" {
  for_each  = var.cloudrun_sa_email != null ? google_secret_manager_secret.secrets : {}
  secret_id = each.value.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.cloudrun_sa_email}"
}
