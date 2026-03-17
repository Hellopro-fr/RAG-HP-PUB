variable "name" {
  description = "Name of the VM"
  type        = string
}

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "zone" {
  description = "Zone (e.g. europe-west1-b)"
  type        = string
}

variable "machine_type" {
  description = "GCE machine type (e.g. e2-small)"
  type        = string
  default     = "e2-small"
}

variable "image" {
  description = "Boot disk image"
  type        = string
  default     = "debian-cloud/debian-12"
}

variable "disk_size_gb" {
  type    = number
  default = 10
}

variable "disk_type" {
  type    = string
  default = "pd-standard"
}
variable "network" {
  description = "VPC network name"
  type        = string
}

variable "subnetwork" {
  description = "Subnetwork name"
  type        = string
}

variable "tags" {
  description = "Network tags"
  type        = list(string)
  default     = []
}
