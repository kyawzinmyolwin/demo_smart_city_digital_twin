"""
AWS Lambda handlers for the Christchurch CBD metrics WebSocket API.

This is the only module in the cloud package that talks to AWS. It sits behind
an API Gateway WebSocket API (provisioned by ../../infra) with three routes:

    $connect     -> on_connect      register the caller in the connections table
    $disconnect  -> on_disconnect   forget it
    tick         -> on_tick         aggregate a snapshot and fan metrics out

Message flow
------------
The simulation side (the Phase 1 emitter, bridged to this API) sends a message
of the form ``{"action": "tick", "snapshot": {<emitter snapshot>}}``. API
Gateway routes it here by the ``action`` field (the route selection expression
is ``$request.body.action``). ``on_tick`` aggregates the snapshot via the pure
``aggregate.aggregate_snapshot`` and pushes the resulting metrics to every
connected dashboard client through the API Gateway Management API.

Everything AWS-shaped is kept thin so the interesting logic stays in the pure,
unit-tested ``aggregate`` module.

Environment variables (set by Terraform):
    CONNECTIONS_TABLE  DynamoDB table name holding active connection ids.
    FREE_FLOW_MPS      Optional override for the congestion-index free-flow speed.
"""
from __future__ import annotations

import json
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from aggregate import DEFAULT_FREE_FLOW_MPS, aggregate_snapshot

_CONNECTIONS_TABLE = os.environ.get("CONNECTIONS_TABLE", "")
_FREE_FLOW_MPS = float(os.environ.get("FREE_FLOW_MPS", DEFAULT_FREE_FLOW_MPS))

# Reused across warm invocations. DynamoDB resource is region-implicit (Lambda
# runtime provides AWS_REGION); the management client is endpoint-specific so it
# is built per invocation from the event's domain/stage in _management_client.
_dynamodb = boto3.resource("dynamodb")
_connections = _dynamodb.Table(_CONNECTIONS_TABLE) if _CONNECTIONS_TABLE else None


def _ok(body: str = "OK") -> dict[str, Any]:
    return {"statusCode": 200, "body": body}


def on_connect(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    """$connect route: record the new connection id so ticks can reach it."""
    connection_id = event["requestContext"]["connectionId"]
    _connections.put_item(Item={"connectionId": connection_id})
    return _ok("connected")


def on_disconnect(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    """$disconnect route: drop the connection id."""
    connection_id = event["requestContext"]["connectionId"]
    _connections.delete_item(Key={"connectionId": connection_id})
    return _ok("disconnected")


def _management_client(event: dict[str, Any]) -> Any:
    """Build an API Gateway Management API client for this API's stage.

    The @connections endpoint is per-API-per-stage, derived from the request
    context, so it cannot be a module-level constant.
    """
    ctx = event["requestContext"]
    endpoint = "https://{domain}/{stage}".format(
        domain=ctx["domainName"], stage=ctx["stage"]
    )
    return boto3.client("apigatewaymanagementapi", endpoint_url=endpoint)


def _parse_snapshot(event: dict[str, Any]) -> dict[str, Any]:
    """Pull the snapshot out of the incoming WebSocket message body."""
    body = event.get("body") or "{}"
    if isinstance(body, str):
        body = json.loads(body)
    # Accept either {"action":"tick","snapshot":{...}} or a bare snapshot.
    return body.get("snapshot", body)


def on_tick(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    """tick route: aggregate the snapshot and broadcast metrics to clients.

    Returns 200 to the sender regardless of individual client-send failures; a
    stale client is pruned rather than failing the whole tick.
    """
    snapshot = _parse_snapshot(event)
    metrics = aggregate_snapshot(snapshot, free_flow_mps=_FREE_FLOW_MPS)

    # TODO(phase-2, influxdb slice): write `metrics` to InfluxDB Cloud here.
    # Deferred deliberately — this slice is the Lambda + IaC skeleton only.

    _broadcast(event, json.dumps(metrics, separators=(",", ":")))
    return _ok(json.dumps(metrics))


def _broadcast(event: dict[str, Any], message: str) -> None:
    """Send ``message`` to every registered connection, pruning dead ones."""
    if _connections is None:
        return
    management = _management_client(event)
    encoded = message.encode("utf-8")

    scan = _connections.scan(ProjectionExpression="connectionId")
    for item in scan.get("Items", []):
        connection_id = item["connectionId"]
        try:
            management.post_to_connection(
                ConnectionId=connection_id, Data=encoded
            )
        except ClientError as exc:
            # 410 Gone: the client vanished without a clean $disconnect. Prune it.
            if exc.response["Error"]["Code"] == "GoneException":
                _connections.delete_item(Key={"connectionId": connection_id})
            else:
                raise
