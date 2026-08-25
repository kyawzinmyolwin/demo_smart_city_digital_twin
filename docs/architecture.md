# Architecture — Smart City Digital Twin

A Christchurch CBD traffic simulation (SUMO) extended with a real-time cloud data
pipeline and a live browser dashboard. The simulation is the data source; every
step produces fresh per-vehicle state, which is streamed to the cloud, aggregated
into metrics, stored as time-series, and visualised live and historically.

**Stack:** SUMO/TraCI · Python (asyncio + websockets) · AWS (API Gateway WebSocket,
Lambda, DynamoDB, S3, CloudFront, Secrets Manager, CloudWatch) · InfluxDB Cloud ·
Leaflet + Chart.js · Terraform · GitHub Actions.
**Region:** `ap-southeast-2` (billing alarm in `us-east-1`).

---

## System overview

```mermaid
flowchart TB
    subgraph SIM["🖥️ Simulation host (Vagrant VM / Mac Mini)"]
        SUMO["SUMO simulation<br/>Christchurch CBD network + real Miovision demand"]
        TRACI["run_traci.py<br/>TraCI control loop (port 8813)<br/>jumps to 06:30, steps sim"]
        EMIT["emitter.py<br/>serialize_vehicles() → JSON schema<br/>XY→WGS84 via sumolib"]
        SUMO -->|"TraCI :8813"| TRACI
        TRACI -->|"per-step hook"| EMIT
    end

    subgraph LOCALDEV["🧪 Local dev path (optional)"]
        WS["Broadcaster<br/>async WebSocket server :8765"]
        MW["metrics_writer.py<br/>WS feed → compute_tick_metrics"]
        LINFLUX["Local InfluxDB 2.7<br/>docker-compose / Colima"]
        REPLAY["replay_server.py<br/>local mirror of replay Lambda :8788"]
        WS --> MW --> LINFLUX
        LINFLUX --> REPLAY
    end

    subgraph AWS["☁️ AWS — ap-southeast-2 (Terraform: infra/)"]
        APIGW["API Gateway<br/>WebSocket API (public)<br/>routes: $connect / $disconnect / sendmessage / $default"]
        DDB["DynamoDB<br/>connections table"]
        L1["Lambda: traffic-ingest<br/>fan-out to connected clients"]
        L2["Lambda: traffic-metrics<br/>compute_tick_metrics()<br/>flow · avg speed · congestion"]
        L3["Lambda: traffic-replay<br/>Flux range queries (read)"]
        SM["Secrets Manager<br/>InfluxDB All-Access token"]
        S3["S3 bucket<br/>dashboard static host"]
        CF["CloudFront<br/>HTTPS CDN"]
        CW["CloudWatch<br/>log groups (14d) + $5 billing alarm"]

        APIGW --> L1
        APIGW --> L2
        APIGW <--> DDB
        L2 --> SM
        L3 --> SM
        S3 --> CF
        L1 -.-> CW
        L2 -.-> CW
        L3 -.-> CW
    end

    subgraph TSDB["📊 InfluxDB Cloud (free tier)"]
        ICLOUD["Time-series bucket<br/>tick metrics"]
    end

    subgraph CLIENT["🌐 Browser dashboard"]
        MAP["intersection_map.html<br/>Leaflet map + speed-coloured markers<br/>3 Chart.js panels (count / speed / congestion)<br/>pause/resume · History panel"]
    end

    %% Cloud data path (primary)
    EMIT -->|"CloudForwarder<br/>wss:// sendmessage per tick"| APIGW
    L2 -->|"write points"| ICLOUD
    L3 -->|"read range"| ICLOUD

    %% Dashboard wiring
    CF -->|"serves HTML"| MAP
    APIGW -->|"live ticks (WS)"| MAP
    L3 -->|"history (?replay=)"| MAP

    %% Local alternative feeds
    EMIT -.->|"--emit :8765"| WS
    MAP -.->|"local dev"| REPLAY

    classDef sim fill:#e8f0fe,stroke:#4285f4,color:#111
    classDef aws fill:#fff4e5,stroke:#ff9900,color:#111
    classDef tsdb fill:#e6f4ea,stroke:#34a853,color:#111
    classDef client fill:#f3e8fd,stroke:#a142f4,color:#111
    classDef localdev fill:#f5f5f5,stroke:#9aa0a6,color:#111

    class SUMO,TRACI,EMIT sim
    class APIGW,DDB,L1,L2,L3,SM,S3,CF,CW aws
    class ICLOUD tsdb
    class MAP client
    class WS,MW,LINFLUX,REPLAY localdev
```

---

## Real-time data flow (per simulation tick)

```mermaid
sequenceDiagram
    participant S as SUMO
    participant R as run_traci.py + emitter.py
    participant G as API Gateway (WS)
    participant I as Lambda traffic-ingest
    participant M as Lambda traffic-metrics
    participant D as InfluxDB Cloud
    participant B as Browser dashboard

    S->>R: simulationStep()
    R->>R: serialize_vehicles() — XY→WGS84, build JSON
    R->>G: {"action":"sendmessage","data":{tick, vehicles[…]}}
    G->>I: route sendmessage
    I->>B: fan-out live snapshot (WS)
    G->>M: route sendmessage
    M->>M: compute_tick_metrics() — flow, avg speed, congestion
    M->>D: write time-series point
    Note over B: markers move + Chart.js panels update
    B->>D: (history) via traffic-replay Lambda, Flux range query
```

---

## Layers

| Layer | Components | Notes |
|---|---|---|
| **Simulation** | SUMO, `run_traci.py`, `emitter.py` | TraCI on `:8813`. `serialize_vehicles()` converts SUMO XY → WGS84 (`sumolib`). `CloudForwarder` dials API Gateway; resilient (reconnects, never crashes the sim). Throttle with `--emit-interval`. |
| **Ingress** | API Gateway WebSocket API | Public endpoint. Routes `$connect`/`$disconnect`/`sendmessage`/`$default`. Connection IDs tracked in DynamoDB. |
| **Compute** | 3 Lambdas | `traffic-ingest` (fan-out), `traffic-metrics` (`compute_tick_metrics`, kept in sync with `scripts/metrics.py`), `traffic-replay` (read/range). |
| **Storage** | InfluxDB Cloud, DynamoDB, S3, Secrets Manager | Time-series → InfluxDB Cloud (not local Docker). Token in Secrets Manager, never hardcoded. Dashboard on S3. |
| **Delivery** | CloudFront | HTTPS CDN in front of the S3-hosted dashboard. |
| **Presentation** | `intersection_map.html` | Leaflet + speed-coloured markers + 3 Chart.js panels + pause/resume + History panel (`?replay=<url>`). |
| **Observability** | CloudWatch | One log group per Lambda (14-day retention) + $5 billing alarm (`us-east-1`). |
| **IaC / CI** | Terraform (`infra/`), GitHub Actions | S3 + DynamoDB backend for state. |

---

## Local development path

For offline work the emitter's `--emit` WebSocket server (`:8765`) feeds
`metrics_writer.py` → **local InfluxDB** (Docker Compose / Colima), and
`replay_server.py` (`:8788`) mirrors the replay Lambda so the dashboard's history
panel works without touching AWS. The browser points at it with `?replay=http://localhost:8788/metrics`.

## Known open items

- **Replay public-URL access (403):** the replay Lambda Function URL denies anonymous
  access on this account; front it with API Gateway (or IAM-signed requests) so the
  deployed dashboard's history charts work.
- **Dashboard upload:** push `intersection_map.html` to S3 + CloudFront invalidation so
  the hosted copy matches the current version.
