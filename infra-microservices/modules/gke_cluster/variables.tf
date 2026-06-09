variable "project_id" {}
variable "subnetwork" {}
variable "network" {}
variable "gke_cluster_nb_nodes" {}
variable "gke_cluster_nb_nodes_final" {}
variable "gke_type_machine" {}
variable "zone" {}
variable "node_ntwk_tag" {

  type    = list(any)
  default = []
}
variable "name" {}
variable "cidr_range_pods" {}
variable "cidr_range_svcs" {}
variable "cidr_range_master" {}
variable "master_authorized_networks_0" {}