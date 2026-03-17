output "notification_channel_id" {
  description = "ID du canal de notification email"
  value       = google_monitoring_notification_channel.email.id
}
