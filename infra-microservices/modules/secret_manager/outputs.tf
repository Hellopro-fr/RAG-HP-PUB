output "secret_ids" {
  description = "Map des secret IDs crees"
  value       = { for k, v in google_secret_manager_secret.secrets : k => v.id }
}
