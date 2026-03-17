# =============================================================================
# DNS Records Module - main.tf
# Creates DNS A records for internal services
# =============================================================================

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "managed_zone" {
  description = "Name of the managed DNS zone"
  type        = string
}

variable "dns_zone" {
  description = "DNS zone suffix (e.g., hello.dev.private.com.)"
  type        = string
}

variable "records" {
  description = "Map of DNS records to create"
  type = map(object({
    name = string
    ip   = string
    ttl  = optional(number, 300)
  }))
  default = {}
}

# =============================================================================
# Resources
# =============================================================================

resource "google_dns_record_set" "records" {
  for_each = var.records

  project      = var.project_id
  name         = "${each.value.name}.${var.dns_zone}"
  type         = "A"
  ttl          = each.value.ttl
  managed_zone = var.managed_zone
  rrdatas      = [each.value.ip]
}

# =============================================================================
# Outputs
# =============================================================================

output "record_names" {
  description = "Map of record names created"
  value       = { for k, v in google_dns_record_set.records : k => v.name }
}

output "record_ips" {
  description = "Map of record IPs"
  value       = { for k, v in google_dns_record_set.records : k => v.rrdatas[0] }
}
