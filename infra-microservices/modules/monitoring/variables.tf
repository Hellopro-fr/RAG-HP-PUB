variable "project_id" {
  description = "ID du projet GCP"
  type        = string
}

variable "environment" {
  description = "Environnement (dev, staging, prod)"
  type        = string
}

variable "alert_email" {
  description = "Adresse email pour les alertes"
  type        = string
}

variable "monthly_budget" {
  description = "Budget mensuel en euros"
  type        = number
  default     = 400
}

variable "billing_account_id" {
  description = "ID du compte de facturation GCP (vide = pas de budget)"
  type        = string
  default     = ""
}
