variable "secrets" {
  description = "Map des secrets a creer. Cle = secret_id, valeur = metadata"
  type = map(object({
    service = string
  }))
  default = {}
}

variable "common_labels" {
  description = "Labels communs appliques a toutes les ressources"
  type        = map(string)
  default     = {}
}

variable "cloudrun_sa_email" {
  description = "Email du SA Cloud Run runtime. Recoit roles/secretmanager.secretAccessor sur chaque secret du module (granulaire, least privilege). Null = pas de binding cree."
  type        = string
  default     = null
}
