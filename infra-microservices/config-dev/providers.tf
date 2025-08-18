terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.45.0"
    }
  }

  required_version = ">= 1.11.4"
}