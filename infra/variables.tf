# Input variables. Defaults are chosen for this project; override per-environment
# values in terraform.tfvars (see terraform.tfvars.example). Never put secrets
# here — the InfluxDB token goes into Secrets Manager by hand (see README).

variable "aws_region" {
  description = "AWS region. ap-southeast-2 (Sydney) is the closest region to NZ."
  type        = string
  default     = "ap-southeast-2"
}

variable "project" {
  description = "Project name, used as a prefix for resource names and tags."
  type        = string
  default     = "christchurch-digital-twin"
}

variable "environment" {
  description = "Deployment environment (prod, dev, ...). Part of resource names."
  type        = string
  default     = "prod"
}

variable "dashboard_bucket_name" {
  description = <<-EOT
    Globally-unique S3 bucket name to host the static dashboard. S3 bucket names
    share one global namespace, so this cannot have a sensible default — pick
    something unique, e.g. "christchurch-digital-twin-dashboard-<your-initials>".
  EOT
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the Lambda log groups (Phase 2b)."
  type        = number
  default     = 14
}

variable "billing_alarm_threshold_usd" {
  description = "Estimated-charges alarm threshold in USD. Keep this low for a student project."
  type        = number
  default     = 5
}

variable "alarm_email" {
  description = "Email address subscribed to the billing alarm SNS topic. You must confirm the subscription from your inbox after apply."
  type        = string
}

# --- InfluxDB Cloud (used by storage.tf; fill in once you have an account) ------

variable "influxdb_url" {
  description = "InfluxDB Cloud regional URL, e.g. https://us-east-1-1.aws.cloud2.influxdata.com"
  type        = string
  default     = ""
}

variable "influxdb_org" {
  description = "InfluxDB Cloud organization name."
  type        = string
  default     = ""
}

variable "influxdb_bucket_name" {
  description = "InfluxDB bucket for tick metrics."
  type        = string
  default     = "traffic-metrics"
}

variable "influxdb_retention_seconds" {
  description = "Retention period for the InfluxDB bucket in seconds (0 = infinite; free tier max is 30 days = 2592000)."
  type        = number
  default     = 2592000
}
