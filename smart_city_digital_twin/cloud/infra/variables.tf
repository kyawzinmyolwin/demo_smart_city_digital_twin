variable "aws_region" {
  description = "AWS region to deploy into. ap-southeast-2 (Sydney) is closest to NZ."
  type        = string
  default     = "ap-southeast-2"
}

variable "project_name" {
  description = "Prefix for all resource names."
  type        = string
  default     = "christchurch-twin"
}

variable "stage_name" {
  description = "API Gateway WebSocket stage name."
  type        = string
  default     = "dev"
}

variable "free_flow_mps" {
  description = <<-EOT
    Free-flow reference speed (m/s) for the congestion index, passed to the
    Lambda as an env var. Default 13.889 = 50 km/h (NZ urban limit).
  EOT
  type        = number
  default     = 13.889
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the Lambda functions."
  type        = number
  default     = 14
}
