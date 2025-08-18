variable "project_id" {}
variable region  {
    description = "Registries region"
    type        = string
    default     = "europe-west1"
}

variable "repository_id" {
  description = "ID du repository"
  type        = string
}

variable "description" {
  description = "Description du repository"
  type        = string
  default     = ""
}



variable "immutable_tags" {
  description = "Interdire les retags (Docker)"
  type        = bool
  default     = false
}
