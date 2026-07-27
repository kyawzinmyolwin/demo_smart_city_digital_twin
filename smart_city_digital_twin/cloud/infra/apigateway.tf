# WebSocket API. Routes are selected by the `action` field of each JSON message
# body, so a message like {"action":"tick","snapshot":{...}} lands on the `tick`
# route; $connect/$disconnect are the built-in lifecycle routes.
resource "aws_apigatewayv2_api" "metrics" {
  name                       = "${local.name_prefix}-metrics"
  protocol_type              = "WEBSOCKET"
  route_selection_expression = "$request.body.action"
}

# --- integrations (one per Lambda) ----------------------------------------
resource "aws_apigatewayv2_integration" "connect" {
  api_id                    = aws_apigatewayv2_api.metrics.id
  integration_type          = "AWS_PROXY"
  integration_uri           = aws_lambda_function.connect.invoke_arn
  content_handling_strategy = "CONVERT_TO_TEXT"
}

resource "aws_apigatewayv2_integration" "disconnect" {
  api_id                    = aws_apigatewayv2_api.metrics.id
  integration_type          = "AWS_PROXY"
  integration_uri           = aws_lambda_function.disconnect.invoke_arn
  content_handling_strategy = "CONVERT_TO_TEXT"
}

resource "aws_apigatewayv2_integration" "tick" {
  api_id                    = aws_apigatewayv2_api.metrics.id
  integration_type          = "AWS_PROXY"
  integration_uri           = aws_lambda_function.tick.invoke_arn
  content_handling_strategy = "CONVERT_TO_TEXT"
}

# --- routes ----------------------------------------------------------------
resource "aws_apigatewayv2_route" "connect" {
  api_id    = aws_apigatewayv2_api.metrics.id
  route_key = "$connect"
  target    = "integrations/${aws_apigatewayv2_integration.connect.id}"
}

resource "aws_apigatewayv2_route" "disconnect" {
  api_id    = aws_apigatewayv2_api.metrics.id
  route_key = "$disconnect"
  target    = "integrations/${aws_apigatewayv2_integration.disconnect.id}"
}

resource "aws_apigatewayv2_route" "tick" {
  api_id    = aws_apigatewayv2_api.metrics.id
  route_key = "tick"
  target    = "integrations/${aws_apigatewayv2_integration.tick.id}"
}

# --- stage (auto-deployed) -------------------------------------------------
resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.metrics.id
  name        = var.stage_name
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = 50
    throttling_rate_limit  = 50
  }
}
