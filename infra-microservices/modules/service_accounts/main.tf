# =============================================================================
# Module: Service Accounts CI/CD
# Gestion des Service Accounts pour pipelines et services
# Source: Extrait de infra-ci-cd/terraform/main.tf (lignes 51-91)
# =============================================================================

# Service Account pour Cloud Build
resource "google_service_account" "cloud_build_sa" {
  account_id   = "cloud-build-deployer"
  display_name = "Cloud Build Service Account"
  description  = "Service account utilise par Cloud Build pour build et deploy"
  project      = var.project_id
}

# Permissions pour Cloud Build SA
resource "google_project_iam_member" "cloud_build_roles" {
  for_each = toset([
    "roles/artifactregistry.writer",
    "roles/cloudbuild.builds.builder",
    "roles/run.admin",
    "roles/compute.instanceAdmin.v1",
    "roles/storage.objectViewer",
    "roles/logging.logWriter",
  ])

  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.cloud_build_sa.email}"
}

# Service Account pour CloudRun services
resource "google_service_account" "cloudrun_sa" {
  account_id   = "cloudrun-services"
  display_name = "CloudRun Services Account"
  description  = "Service account pour les services CloudRun (moindre privilege)"
  project      = var.project_id
}

# Permissions minimales pour CloudRun SA
resource "google_project_iam_member" "cloudrun_sa_roles" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/cloudtrace.agent",
  ])

  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.cloudrun_sa.email}"
}

# Service Accounts dedies par domaine (Phase 3 - IAM least privilege)
resource "google_service_account" "dedicated_sa" {
  for_each = var.dedicated_service_accounts

  account_id   = each.key
  display_name = each.value.display_name
  description  = each.value.description
  project      = var.project_id
}

resource "google_project_iam_member" "dedicated_sa_roles" {
  for_each = {
    for pair in flatten([
      for sa_key, sa in var.dedicated_service_accounts : [
        for role in sa.roles : {
          key  = "${sa_key}-${role}"
          sa   = sa_key
          role = role
        }
      ]
    ]) : pair.key => pair
  }

  project = var.project_id
  role    = each.value.role
  member  = "serviceAccount:${google_service_account.dedicated_sa[each.value.sa].email}"
}
