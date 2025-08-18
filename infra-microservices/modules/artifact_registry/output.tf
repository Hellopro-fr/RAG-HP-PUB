output "artifact_registry_name" {
  description = "Nom du repository Artifact Registry"
  value       = google_artifact_registry_repository.artifactory.name
  
}