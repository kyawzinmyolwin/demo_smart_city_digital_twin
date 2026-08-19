# Registry of active WebSocket connections. The tick handler scans this table to
# fan aggregated metrics out to every connected dashboard client. On-demand
# billing keeps it free-tier friendly for a prototype with a handful of clients.
resource "aws_dynamodb_table" "connections" {
  name         = "${local.name_prefix}-connections"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "connectionId"

  attribute {
    name = "connectionId"
    type = "S"
  }
}
