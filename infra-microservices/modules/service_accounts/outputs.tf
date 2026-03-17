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
