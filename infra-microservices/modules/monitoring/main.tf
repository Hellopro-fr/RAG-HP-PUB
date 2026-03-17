# =============================================================================
# Module: Monitoring & Alerting
# Alertes Cloud Monitoring et budget
# Source: Extrait de infra-ci-cd/terraform/main.tf (lignes 202-273)
# =============================================================================

# Canal de notification par email
resource "google_monitoring_notification_channel" "email" {
  display_name = "Email Alerts RAG-HP ${var.environment}"
  type         = "email"

  labels = {
    email_address = var.alert_email
  }

  enabled = true
}

# Alerte pour erreurs CloudRun
resource "google_monitoring_alert_policy" "cloudrun_errors" {
  display_name = "CloudRun - Taux d'erreur eleve (${var.environment})"
  combiner     = "OR"

  conditions {
    display_name = "Erreur rate > 5%"

    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND metric.type = \"run.googleapis.com/request_count\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.05

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  alert_strategy {
    auto_close = "1800s"
  }
}

# Alerte GKE CPU > 80% sustained 5min
resource "google_monitoring_alert_policy" "gke_cpu_high" {
  display_name = "GKE - CPU > 80% sustained 5min (${var.environment})"
  combiner     = "OR"

  conditions {
    display_name = "GKE node CPU > 80%"

    condition_threshold {
      filter          = "resource.type = \"k8s_node\" AND metric.type = \"kubernetes.io/node/cpu/allocatable_utilization\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.8

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  alert_strategy {
    auto_close = "1800s"
  }
}

# Alerte PVC disk usage > 85%
resource "google_monitoring_alert_policy" "disk_usage_high" {
  display_name = "GKE - PVC Disk Usage > 85% (${var.environment})"
  combiner     = "OR"

  conditions {
    display_name = "PVC disk usage > 85%"

    condition_threshold {
      filter          = "resource.type = \"k8s_pod\" AND metric.type = \"kubernetes.io/pod/volume/utilization\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.85

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  alert_strategy {
    auto_close = "1800s"
  }
}

# Budget mensuel avec alertes
resource "google_billing_budget" "monthly_budget" {
  count           = var.billing_account_id != "" ? 1 : 0
  billing_account = var.billing_account_id
  display_name    = "Budget mensuel RAG-HP (${var.environment})"

  budget_filter {
    projects = ["projects/${var.project_id}"]
  }

  amount {
    specified_amount {
      currency_code = "EUR"
      units         = tostring(var.monthly_budget)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }

  threshold_rules {
    threshold_percent = 0.8
  }

  threshold_rules {
    threshold_percent = 1.0
  }

  all_updates_rule {
    monitoring_notification_channels = [google_monitoring_notification_channel.email.id]
  }
}
