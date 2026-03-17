variable "project_id" {
  description = "ID du projet GCP"
  type        = string
}

variable "region" {
  description = "Region GCP"
  type        = string
}

variable "network" {
  description = "Nom du VPC network"
  type        = string
}

variable "environment" {
  description = "Environnement (dev, staging, prod)"
  type        = string
}
