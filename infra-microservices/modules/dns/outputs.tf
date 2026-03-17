output "dns_zone" {
  description = "Nom de la DNS"
  value       = google_dns_managed_zone.private_zone.dns_name
}
output "dns_name" {
  description = "Nom de la DNS"
  value       = google_dns_managed_zone.private_zone.name
}
output "dns_id" {
  description = "Nom de la DNS"
  value       = google_dns_managed_zone.private_zone.id
}
