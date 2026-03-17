output "cluster_ip" {
  value = google_container_cluster.gke_cluster.endpoint
}

output "cluster_name" {
  value = google_container_cluster.gke_cluster.name
}
