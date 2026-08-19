# ---------------------------------------------------------------------------
# IAM: one execution role shared by the connect/disconnect/tick functions.
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.name_prefix}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# Least-privilege inline policy: logs, the connections table, and the ability to
# post back to WebSocket clients via the API Gateway Management API.
data "aws_iam_policy_document" "lambda_permissions" {
  statement {
    sid = "Logs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:*:*:*"]
  }

  statement {
    sid = "ConnectionsTable"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:DeleteItem",
      "dynamodb:Scan",
    ]
    resources = [aws_dynamodb_table.connections.arn]
  }

  statement {
    sid       = "ManageConnections"
    actions   = ["execute-api:ManageConnections"]
    resources = ["${aws_apigatewayv2_api.metrics.execution_arn}/*"]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${local.name_prefix}-lambda"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

# ---------------------------------------------------------------------------
# The three functions. Same code bundle, different handler entrypoints.
# ---------------------------------------------------------------------------
locals {
  lambda_env = {
    CONNECTIONS_TABLE = aws_dynamodb_table.connections.name
    FREE_FLOW_MPS     = tostring(var.free_flow_mps)
  }
}

resource "aws_lambda_function" "connect" {
  function_name    = "${local.name_prefix}-connect"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "handlers.on_connect"
  filename         = data.archive_file.metrics_lambda.output_path
  source_code_hash = data.archive_file.metrics_lambda.output_base64sha256
  timeout          = 10

  environment {
    variables = local.lambda_env
  }
}

resource "aws_lambda_function" "disconnect" {
  function_name    = "${local.name_prefix}-disconnect"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "handlers.on_disconnect"
  filename         = data.archive_file.metrics_lambda.output_path
  source_code_hash = data.archive_file.metrics_lambda.output_base64sha256
  timeout          = 10

  environment {
    variables = local.lambda_env
  }
}

resource "aws_lambda_function" "tick" {
  function_name    = "${local.name_prefix}-tick"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "handlers.on_tick"
  filename         = data.archive_file.metrics_lambda.output_path
  source_code_hash = data.archive_file.metrics_lambda.output_base64sha256
  timeout          = 15

  environment {
    variables = local.lambda_env
  }
}

# Explicit log groups so retention is managed (Lambda would otherwise create
# them with never-expire retention).
resource "aws_cloudwatch_log_group" "connect" {
  name              = "/aws/lambda/${aws_lambda_function.connect.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "disconnect" {
  name              = "/aws/lambda/${aws_lambda_function.disconnect.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "tick" {
  name              = "/aws/lambda/${aws_lambda_function.tick.function_name}"
  retention_in_days = var.log_retention_days
}

# Allow API Gateway to invoke each function.
resource "aws_lambda_permission" "connect" {
  statement_id  = "AllowInvokeFromApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.connect.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.metrics.execution_arn}/*/*"
}

resource "aws_lambda_permission" "disconnect" {
  statement_id  = "AllowInvokeFromApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.disconnect.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.metrics.execution_arn}/*/*"
}

resource "aws_lambda_permission" "tick" {
  statement_id  = "AllowInvokeFromApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.tick.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.metrics.execution_arn}/*/*"
}
