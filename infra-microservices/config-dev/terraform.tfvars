project_id = "hellopro-rag-project"
region     = "europe-west1"
subnetworks = [
    {
      name          = "hellopro-subnet-dev"
      ip_cidr_range = "10.0.1.0/24"
      region        = "europe-west1"
    }
  ]
zone       = "europe-west1-b"
subnetwork = "hellopro-subnet-dev"
repository_id = "hellopro"
zone_name ="hellopro-private"
dns_name ="hello.dev.private.com."


proxy_subnet_prefix = "10.0.125.0/24"