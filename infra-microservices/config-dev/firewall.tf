resource "google_compute_firewall" "allow_ssh" {
  name    = "allow-ssh"
  network    = module.vpc.vpc_name
  direction = "INGRESS"
  priority  = 1000
  allow {
    protocol = "tcp"
    ports    = ["22","19530","80"]
  }
  target_tags = ["${var.node_ntwk_tag[0]}"]
  source_ranges = ["0.0.0.0/0"]  # 🔁 Restreins à une IP ou CIDR privé si besoin
  description   = "Allow SSH access to instances with tag 'ssh'"
}

resource "google_compute_firewall" "allow-intra-lan" {
  name    = "allow-intra-lan"
  network    = module.vpc.vpc_name

  allow {
    protocol = "all"
  }
  source_ranges = ["0.0.0.0/0"]

}