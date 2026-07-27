locals {
  name_prefix = "${var.project_name}-${var.stage_name}"

  # Path to the Lambda source relative to this infra dir. The whole metrics/
  # package is zipped; handlers.py imports aggregate.py as a sibling module.
  lambda_source_dir = "${path.module}/../lambda/metrics"
}

# Zip the Lambda source at plan time. Any change to a file under metrics/ changes
# the archive hash, which forces a Lambda update on the next apply.
data "archive_file" "metrics_lambda" {
  type        = "zip"
  source_dir  = local.lambda_source_dir
  output_path = "${path.module}/build/metrics_lambda.zip"
}
