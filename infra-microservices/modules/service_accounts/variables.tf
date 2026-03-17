variable "project_id" {
  description = "ID du projet GCP"
  type        = string
}

variable "dedicated_service_accounts" {
  description = "Map des service accounts dedies a creer"
  type = map(object({
    display_name = string
    description  = string
    roles        = list(string)
  }))
  default = {}
}
