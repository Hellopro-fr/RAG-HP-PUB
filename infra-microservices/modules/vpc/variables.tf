variable "name" {
  description = "The name of the VPC network"
  type        = string
}

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "subnetworks" {
  description = "List of subnetworks"
  type = list(object({
    name          = string
    ip_cidr_range = string
    region        = string
  }))
}
variable "proxy_subnet_prefix" {}

variable "cidr_range_pods" {}
variable "cidr_range_svcs" {}
variable "cidr_range_master" {}