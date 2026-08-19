# Cloud metrics pipeline (Phase 2)

Serverless metrics-aggregation layer for the Christchurch CBD digital twin. It
takes the per-tick vehicle snapshots produced by the Phase 1 emitter
(`../2D_simulation/scripts/emitter.py`), aggregates them into traffic metrics,
and fans those metrics out to connected dashboard clients over WebSocket.

This directory is the **Lambda + Infrastructure-as-Code skeleton**. It is
code-only: everything here is deployable, but nothing has been deployed — that
needs your AWS account and credentials.

## Architecture

```
 SUMO + emitter  ──wss──►  API Gateway  ──►  Lambda (tick)  ──►  dashboard clients
 (Phase 1)                 WebSocket API      metrics/aggregate      (wss fan-out)
                               │                     │
                          $connect/$disconnect       └─►  InfluxDB  (next slice, TODO)
                               │
                           DynamoDB (connection registry)
```

- **API Gateway WebSocket API** — the public `wss://` endpoint. Routes messages
  by their `action` field: `$connect`, `$disconnect`, and `tick`.
- **Lambda** — three handlers sharing one code bundle:
  - `on_connect` / `on_disconnect` register/forget a connection id in DynamoDB.
  - `on_tick` aggregates an incoming snapshot and broadcasts the metrics to every
    registered connection via the API Gateway Management API.
- **DynamoDB** — a pay-per-request table of active connection ids, used by the
  tick handler to know who to broadcast to.

## Layout

```
cloud/
├── lambda/
│   ├── metrics/
│   │   ├── aggregate.py    # pure per-tick metrics — AWS-free, unit-tested
│   │   ├── handlers.py     # $connect / $disconnect / tick Lambda handlers
│   │   └── __init__.py
│   ├── requirements.txt    # runtime deps (boto3 is provided by the runtime)
│   └── tests/
│       └── test_aggregate.py
└── infra/                  # Terraform for API Gateway + Lambda + DynamoDB + IAM
    ├── versions.tf  variables.tf  main.tf
    ├── apigateway.tf  lambda.tf  dynamodb.tf  outputs.tf
    └── terraform.tfvars.example
```

## Metrics produced each tick

| Field             | Meaning |
|-------------------|---------|
| `vehicleCount`    | Vehicles on the network this tick. |
| `avgSpeedMps` / `avgSpeedKmh` | Mean speed across all vehicles. |
| `stoppedCount` / `movingCount` | Split at 0.5 m/s (queue indicator). |
| `congestionIndex` | `1 - avgSpeed/freeFlow`, clamped to `[0,1]`. 0 = free-flowing, 1 = stopped. |
| `flowIndex`       | `vehicleCount * avgSpeedKmh` — a *relative* throughput proxy (`q = k·v`), for trends/scenario comparison, not an absolute veh/h count. |

The aggregation logic lives entirely in `metrics/aggregate.py` and is pure, so
it is tested with plain dicts and no cloud stack.

## Run the tests

```bash
cd cloud/lambda
python -m pytest tests/          # or: python tests/test_aggregate.py
```

## Deploy (when you have AWS credentials)

```bash
cd cloud/infra
terraform init
terraform plan      # review; region defaults to ap-southeast-2 (Sydney)
terraform apply
terraform output websocket_url   # wss:// endpoint for the dashboard + sim bridge
```

Configure via `terraform.tfvars` (see `terraform.tfvars.example`) — region,
name prefix, stage, and the `free_flow_mps` congestion reference.

## Not in this slice (deferred, tracked in the roadmap)

- **InfluxDB write path** — `on_tick` has a marked `TODO` where metrics get
  persisted to InfluxDB Cloud. That is the next Phase 2 slice.
- **Sim → cloud bridge** — a small client that pipes the local emitter's
  snapshots into this API's `tick` route. Trivial to add once the endpoint
  exists; kept out to keep this slice focused on Lambda + IaC.
- **GitHub Actions CI/CD** — running these tests and a `terraform plan` on PRs.

> Terraform was chosen over AWS CDK for the skeleton: declarative, no bootstrap
> step, and each resource reads plainly for review. CDK (Python) remains a valid
> alternative if the project later prefers one language across sim and infra.
