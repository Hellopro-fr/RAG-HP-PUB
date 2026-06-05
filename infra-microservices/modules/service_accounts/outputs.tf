output "cloud_build_sa_email" {
  description = "Email du service account Cloud Build"
  value       = google_service_account.cloud_build_sa.email
}

output "cloudrun_sa_email" {
  description = "Email du service account CloudRun"
  value       = google_service_account.cloudrun_sa.email
}

output "dedicated_sa_emails" {
  description = "Map des emails des service accounts dedies"
  value       = { for k, v in google_service_account.dedicated_sa : k => v.email }
}

# =============================================================================
# Workload Identity Federation - GitHub Actions
# Ces outputs sont utilises pour configurer le workflow deploy-cloud-run.yml
# =============================================================================

output "github_deployer_email" {
  description = "Email du SA github-deployer. A configurer en Repository Variable GitHub : GCP_DEPLOYER_SA"
  value       = google_service_account.github_deployer.email
}

output "wif_provider_name" {
  description = "Nom complet du Workload Identity Provider. A configurer en Repository Variable GitHub : GCP_WIF_PROVIDER (format: projects/<num>/locations/global/workloadIdentityPools/github-pool/providers/github-provider)"
  value       = google_iam_workload_identity_pool_provider.github_provider.name
}

output "wif_pool_name" {
  description = "Nom du Workload Identity Pool (pour debugging et reference)"
  value       = google_iam_workload_identity_pool.github_pool.name
}
