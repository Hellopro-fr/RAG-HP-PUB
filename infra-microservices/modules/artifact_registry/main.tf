resource "google_artifact_registry_repository" "artifactory" {
  location      = "europe-west1"
  repository_id = var.repository_id
  description   = var.description
  format        = "DOCKER"

  # =============================================================================
  # Cleanup policies (Ticket 001-INFRA-GCP-ARCHI Sprint 001 Action 1.11)
  # Appliquees initialement via gcloud CLI puis reconciliees Terraform.
  # Source : modules/artifact_registry/cleanup-policies.json
  # =============================================================================

  # Safety belt : conserve toujours les 10 plus recentes versions
  cleanup_policies {
    id     = "keep-latest-10"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }

  # Supprime les images untagged > 7 jours (~30 images, ~$4/mois gagne)
  cleanup_policies {
    id     = "delete-untagged-7d"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "604800s" # 7 jours
    }
  }

  # Supprime les images tagged > 365 jours (long-tail)
  cleanup_policies {
    id     = "delete-tagged-old-365d"
    action = "DELETE"
    condition {
      tag_state  = "TAGGED"
      older_than = "31536000s" # 365 jours
    }
  }
}
