terraform {
  backend "gcs" {
    bucket  = "hellopro-terraform-state"
    prefix  = "dev/state"
  }
}