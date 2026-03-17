output "router_name" {
  description = "Nom du Cloud Router"
  value       = google_compute_router.router.name
}

output "nat_name" {
  description = "Nom du Cloud NAT"
  value       = google_compute_router_nat.nat.name
}
