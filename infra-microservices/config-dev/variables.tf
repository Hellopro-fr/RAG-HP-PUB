variable project_id {}
variable zone {}
variable region  {}
variable subnetwork {}
variable "subnetworks" {
  description = "List of subnetworks"
  type = list(object({
    name          = string
    ip_cidr_range = string
    region        = string
  }))
}
variable repository_id {}
variable "description" {
  description = "Description du repository"
  type        = string
  default     = ""
}
variable zone_name {}
variable dns_name {}


variable node_ntwk_tag {

  type = list
  default= []
}

variable proxy_subnet_prefix {}
variable ip_cidr_range_vpc_connector_serverless {}