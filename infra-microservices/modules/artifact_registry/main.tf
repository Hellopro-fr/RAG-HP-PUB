resource "google_artifact_registry_repository" "artifactory" {
  location = "europe-west1" 
  repository_id = var.repository_id
  description   = var.description
  format        = "DOCKER"

}
