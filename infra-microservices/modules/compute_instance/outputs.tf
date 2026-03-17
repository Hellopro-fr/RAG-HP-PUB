# =============================================================================
# Outputs for compute_instance module
# =============================================================================

output "instance_name" {
  description = "Instance name"
  value       = google_compute_instance.vm.name
}

output "instance_id" {
  description = "Instance ID"
  value       = google_compute_instance.vm.id
}

output "instance_ip" {
  description = "Internal IP address"
  value       = google_compute_instance.vm.network_interface[0].network_ip
}

output "instance_external_ip" {
  description = "External IP address"
  value       = try(google_compute_instance.vm.network_interface[0].access_config[0].nat_ip, null)
}

output "instance_self_link" {
  description = "Instance self link"
  value       = google_compute_instance.vm.self_link
}
