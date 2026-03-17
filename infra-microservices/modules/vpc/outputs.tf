output "vpc_name" {
  description = "Nom de la VPC créée"
  value       = google_compute_network.vpc.name
}

output "vpc_id" {
  description = "ID complet de la VPC (utile pour référence dans d'autres ressources)"
  value       = google_compute_network.vpc.id
}

output "subnetworks" {
  description = "Liste des sous-réseaux créés (par nom)"
  value = {
    for name, subnet in google_compute_subnetwork.subnets :
    name => {
      name          = subnet.name
      region        = subnet.region
      self_link     = subnet.self_link
      ip_cidr_range = subnet.ip_cidr_range
      network       = subnet.network
    }
  }
}
