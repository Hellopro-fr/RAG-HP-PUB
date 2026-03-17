

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
