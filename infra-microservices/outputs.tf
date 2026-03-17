# =============================================================================
# outputs.tf - Infrastructure Microservices RAG HelloPro
# =============================================================================

# VPC Outputs
output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "vpc_name" {
  description = "VPC Name"
  value       = module.vpc.vpc_name
}

output "subnet_self_links" {
  description = "Map of subnet self links"
  value       = { for k, v in module.vpc.subnetworks : k => v.self_link }
}

# GKE Outputs
output "gke_cluster_name" {
  description = "GKE Cluster name"
  value       = module.gke_cluster.cluster_name
}

output "gke_cluster_endpoint" {
  description = "GKE Cluster endpoint"
  value       = module.gke_cluster.cluster_ip
  sensitive   = true
}

# DNS Outputs
output "dns_zone_name" {
  description = "DNS Zone name"
  value       = module.dns.dns_name
}

# VM Outputs
output "manager_vm_ip" {
  description = "Manager VM internal IP"
  value       = module.vm.instance_ip
}

# Environment info
output "environment" {
  description = "Current environment"
  value       = var.environment
}
