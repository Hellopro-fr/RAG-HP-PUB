resource "google_container_cluster" "gke_cluster" {

  provider = google-beta // required for max pods per pods

  lifecycle {
    prevent_destroy = false
    # Ignorer les changements faits manuellement dans GCP Console
    ignore_changes = [
      release_channel,
      maintenance_policy,
    ]
  }


  deletion_protection = false

  project = var.project_id
  name    = "${var.name}-k8s"

  network    = var.network
  subnetwork = var.subnetwork

  location = var.zone

  initial_node_count = var.gke_cluster_nb_nodes
  ip_allocation_policy {
    cluster_ipv4_cidr_block  = var.cidr_range_pods
    services_ipv4_cidr_block = var.cidr_range_svcs
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = true                  // PRIVATE ENDPOINT
    master_ipv4_cidr_block  = var.cidr_range_master // IP for masters - cannot overlap existing network
  }
  master_authorized_networks_config { // Allow Master Endpoint
    cidr_blocks {
      cidr_block = var.master_authorized_networks_0
    }
  }
  logging_service          = "logging.googleapis.com/kubernetes"
  monitoring_service       = "monitoring.googleapis.com/kubernetes"
  remove_default_node_pool = true
  release_channel {
    channel = "STABLE"
  }



}

resource "google_container_node_pool" "node" {
  project  = var.project_id
  name     = "${var.name}-node"
  location = var.zone
  cluster  = google_container_cluster.gke_cluster.name
  # Comment on prod auto-scalling
  node_count        = var.gke_cluster_nb_nodes_final
  max_pods_per_node = 63

  # Ignorer autoscaling configuré manuellement dans GCP
  lifecycle {
    ignore_changes = [
      autoscaling,
    ]
  }

  # Configuration de l'autoscaling (en prod)
  # autoscaling {
  #   min_node_count = var.gke_cluster_nb_nodes
  #   max_node_count = var.gke_cluster_nb_nodes_final
  # }

  node_config {

    machine_type = var.gke_type_machine
    disk_size_gb = "100" # 1024 en prod

    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/compute",
      "https://www.googleapis.com/auth/devstorage.read_only"
    ]

    metadata = {
      disable-legacy-endpoints = "true"
    }

    tags = [
      var.node_ntwk_tag[0]
    ]
  }
}
