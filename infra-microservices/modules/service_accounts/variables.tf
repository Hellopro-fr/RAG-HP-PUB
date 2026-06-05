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

# =============================================================================
# Workload Identity Federation - GitHub Actions
# =============================================================================

variable "github_org" {
  description = "Organisation GitHub autorisee a utiliser WIF (ex: HelloPro). Filtre attribute_condition pour empecher d'autres orgs d'impersoner le SA."
  type        = string
  validation {
    condition     = length(var.github_org) > 0 && !can(regex("/", var.github_org))
    error_message = "github_org doit etre le nom de l'organisation seul (ex: HelloPro), sans slash."
  }
}

variable "github_repo" {
  description = "Repo GitHub complet au format 'org/repo' (ex: HelloPro/RAG-HP-PUB). Limite l'impersonation aux workflows de ce repo uniquement."
  type        = string
  validation {
    condition     = can(regex("^[^/]+/[^/]+$", var.github_repo))
    error_message = "github_repo doit etre au format 'org/repo' (ex: HelloPro/RAG-HP-PUB)."
  }
}
