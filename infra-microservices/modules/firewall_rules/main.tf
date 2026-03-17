# =============================================================================
# Firewall Rules Module - main.tf
# Creates firewall rules for VPC
# =============================================================================

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "network" {
  description = "VPC network name"
  type        = string
}

variable "rules" {
  description = "Map of firewall rules to create"
  type = map(object({
    name          = string
    description   = optional(string, "")
    direction     = optional(string, "INGRESS")
    priority      = optional(number, 1000)
    source_ranges = list(string)
    target_tags   = optional(list(string), [])
    allow = list(object({
      protocol = string
      ports    = optional(list(string), [])
    }))
    log_config = optional(bool, false)
  }))
  default = {}
}

# =============================================================================
# Resources
# =============================================================================

resource "google_compute_firewall" "rules" {
  for_each = var.rules

  project     = var.project_id
  name        = each.value.name
  network     = var.network
  description = each.value.description
  direction   = each.value.direction
  priority    = each.value.priority

  source_ranges = each.value.source_ranges
  target_tags   = length(each.value.target_tags) > 0 ? each.value.target_tags : null

  dynamic "allow" {
    for_each = each.value.allow
    content {
      protocol = allow.value.protocol
      ports    = length(allow.value.ports) > 0 ? allow.value.ports : null
    }
  }

  dynamic "log_config" {
    for_each = each.value.log_config ? [1] : []
    content {
      metadata = "INCLUDE_ALL_METADATA"
    }
  }
}

# =============================================================================
# Outputs
# =============================================================================

output "firewall_ids" {
  description = "Map of firewall rule IDs"
  value       = { for k, v in google_compute_firewall.rules : k => v.id }
}

output "firewall_names" {
  description = "Map of firewall rule names"
  value       = { for k, v in google_compute_firewall.rules : k => v.name }
}
