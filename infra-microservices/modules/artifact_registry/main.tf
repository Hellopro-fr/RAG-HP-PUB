resource "google_artifact_registry_repository" "artifactory" {
  project = var.project_id
  location = var.region
  repository_id = var.repository_id
  description   = var.description
  format        = "DOCKER"

}
