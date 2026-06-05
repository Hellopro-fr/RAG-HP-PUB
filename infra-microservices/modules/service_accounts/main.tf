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

# =============================================================================
# Workload Identity Federation - GitHub Actions
# Ticket 001-INFRA-GCP-ARCHI Sprint 002 Action 2.2
# Permet a GitHub Actions de s'authentifier a GCP sans cle JSON
# =============================================================================

# Service Account utilise par GitHub Actions via WIF
resource "google_service_account" "github_deployer" {
  account_id   = "github-deployer"
  display_name = "GitHub Actions Deployer (WIF)"
  description  = "Service account utilise par GitHub Actions via Workload Identity Federation. Pas de cle JSON."
  project      = var.project_id
}

# Permissions minimales pour deployer sur Cloud Run + push AR + lire secrets
resource "google_project_iam_member" "github_deployer_roles" {
  for_each = toset([
    "roles/run.developer",                # Deploy services Cloud Run
    "roles/iam.serviceAccountUser",       # Impersonate cloudrun_sa lors du deploy
    "roles/artifactregistry.writer",      # Push images vers Artifact Registry
    "roles/secretmanager.secretAccessor", # Lire les secrets (si necessaire pour deploy)
    "roles/logging.logWriter",            # Ecrire logs CI/CD
  ])

  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

# Workload Identity Pool pour GitHub Actions
resource "google_iam_workload_identity_pool" "github_pool" {
  project                   = var.project_id
  workload_identity_pool_id = "github-pool"
  display_name              = "GitHub Actions Pool"
  description               = "Pool pour authentification GitHub Actions via OIDC (Ticket 001-INFRA-GCP-ARCHI)"
}

# Workload Identity Provider OIDC GitHub
resource "google_iam_workload_identity_pool_provider" "github_provider" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_pool.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub OIDC Provider"
  description                        = "Provider OIDC pour GitHub Actions. Issuer: token.actions.githubusercontent.com"

  attribute_mapping = {
    "google.subject"             = "assertion.sub"
    "attribute.actor"            = "assertion.actor"
    "attribute.repository"       = "assertion.repository"
    "attribute.repository_owner" = "assertion.repository_owner"
    "attribute.ref"              = "assertion.ref"
  }

  # SECURITY : limite WIF aux repos de l'organisation autorisee
  # Sans cette condition, n'importe quel workflow GitHub pourrait s'authentifier
  attribute_condition = "assertion.repository_owner == \"${var.github_org}\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Autorise le repo specifique a impersonate le SA github-deployer
# principalSet limite plus precisement que principal:// (repo entier, tous workflows)
resource "google_service_account_iam_member" "github_deployer_workload_identity" {
  service_account_id = google_service_account.github_deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_pool.name}/attribute.repository/${var.github_repo}"
}
