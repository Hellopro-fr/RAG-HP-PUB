module "artifact_registry" {
  source = "../modules/artifact_registry"
  project_id = var.project_id
  repository_id   = var.repository_id
  description     = "Docker registry for my project"

}
