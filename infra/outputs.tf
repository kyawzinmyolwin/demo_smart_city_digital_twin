# Outputs surfaced after `terraform apply`. These grow as we add the API Gateway
# and CloudFront layers (websocket_url, dashboard_url will land then).

output "dashboard_bucket_name" {
  description = "S3 bucket hosting the dashboard."
  value       = aws_s3_bucket.dashboard.id
}

output "dashboard_bucket_arn" {
  description = "ARN of the dashboard bucket (referenced by the CloudFront OAC policy)."
  value       = aws_s3_bucket.dashboard.arn
}

output "influxdb_token_secret_name" {
  description = "Secrets Manager secret name to populate with the InfluxDB token (put-secret-value)."
  value       = aws_secretsmanager_secret.influxdb_token.name
}

output "influxdb_token_secret_arn" {
  description = "ARN of the InfluxDB token secret (granted to the metrics Lambda)."
  value       = aws_secretsmanager_secret.influxdb_token.arn
}
