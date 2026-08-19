output "websocket_url" {
  description = "wss:// endpoint clients (dashboard and sim bridge) connect to."
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "connections_table" {
  description = "DynamoDB table holding active WebSocket connection ids."
  value       = aws_dynamodb_table.connections.name
}

output "tick_function_name" {
  description = "Name of the metrics-aggregation Lambda (the tick route target)."
  value       = aws_lambda_function.tick.function_name
}
