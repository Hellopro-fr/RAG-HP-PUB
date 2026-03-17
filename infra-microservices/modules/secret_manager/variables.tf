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
