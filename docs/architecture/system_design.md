# UCP Agent Architecture & Integrity Design

This document visualizes the architectural patterns used to guarantee payment integrity and state consistency in the Universal Commerce Protocol (UCP) Agent.

## 1. Deployment Topology (Multi-Worker)

Illustrates why in-memory locks fail and why we enforce safety at the Persistence Layer.
- **Blue Arrows:** Concurrent race attempts.
- **Green Arrow:** The successful write (Winner).
- **Red Dashed Arrows:** Rejection signals (Losers) due to Version Conflict or Unique Constraint.

```mermaid
flowchart TD
    Client["Client / Load Gen"]
    LB["Load Balancer / Port 8000"]
    
    subgraph AppLayer ["Application Layer (Stateless Workers)"]
        direction TB
        style AppLayer fill:#e6f3ff,stroke:#3399ff,stroke-width:1px
        W1["Uvicorn Worker 1"]
        W2["Uvicorn Worker 2"]
        W3["Uvicorn Worker 3"]
        W4["Uvicorn Worker 4"]
    end
    
    subgraph DataLayer ["Persistence Layer (Stateful Source of Truth)"]
        style DataLayer fill:#e6fffa,stroke:#00cc99,stroke-width:1px
        DB[("SQLite DB<br/>(UNIQUE Index)<br/>(Version Column)")]
    end
    
    %% Infrastructure Flow (Neutral)
    Client --> LB
    LB --> W1
    LB --> W2
    LB --> W3
    LB --> W4
    
    %% Outbound Requests (Blue)
    W1 -- "Insert (Ver=1)" --> DB
    W2 -- "Update (Ver=2)" --> DB
    W3 -- "Insert (Ver=1)" --> DB
    W4 -- "Insert (Ver=1)" --> DB
    
    %% Return Signals - SUCCESS (Green)
    DB -- "Success (Committed)" --> W2
    
    %% Return Signals - FAILURE (Red)
    DB -. "StateConflict<br/>(Ver Mismatch)" .-> W1
    DB -. "IntegrityError<br/>(Duplicate)" .-> W3
    DB -. "IntegrityError<br/>(Duplicate)" .-> W4
    
    %% Styling Classes
    classDef worker fill:#fff,stroke:#333,stroke-width:1px;
    class W1,W2,W3,W4 worker;
    
    linkStyle 5,6,7,8 stroke:#007bff,stroke-width:2px;
    linkStyle 9 stroke:#28a745,stroke-width:3px;
    linkStyle 10,11,12 stroke:#dc3545,stroke-width:2px,stroke-dasharray: 5 5;
```

---

## 2. Retry Storm Sequence (Payment Integrity)

Shows how the Database Unique Constraint acts as the "Atomic Guard" against duplicate payments (Double Spend).

```mermaid
sequenceDiagram
    participant Runner as Experiment Runner
    participant Worker as Uvicorn Worker
    participant DB as SQLite DB (Unique Index)

    note over Runner, DB: Scenario: Retry Storm (N=3 Concurrent Requests)

    Runner->>Worker: POST /pay (msgId=101)
    Runner->>Worker: POST /pay (msgId=101)
    Runner->>Worker: POST /pay (msgId=101)

    rect rgb(255, 240, 240)
        note right of Runner: Baseline Mode (Safety Off)
        Worker->>DB: INSERT Order A (No Constraint)
        Worker->>DB: INSERT Order B
        Worker->>DB: INSERT Order C
        DB-->>Worker: Success (3 Orders Created)
        Worker-->>Runner: Return Order A
        Worker-->>Runner: Return Order B
        Worker-->>Runner: Return Order C
    end

    rect rgb(240, 255, 240)
        note right of Runner: Hardened Mode (DB Constraint)
        
        par Parallel Requests
            Worker->>DB: INSERT Order A
        and
            Worker->>DB: INSERT Order A
        and
            Worker->>DB: INSERT Order A
        end

        Note over DB: Constraint Violation Check
        
        DB-->>Worker: Success (Request 1)
        DB--xWorker: ERROR: Unique Constraint (Request 2)
        DB--xWorker: ERROR: Unique Constraint (Request 3)

        par Handling Results
            Worker-->>Runner: Return Order A (Winner)
        and
            Note over Worker: Catch DuplicateOrderError
            Worker->>DB: SELECT * FROM orders WHERE checkout_id=...
            DB-->>Worker: Return Order A
            Worker-->>Runner: Return Order A (Idempotent)
        and
            Note over Worker: Catch DuplicateOrderError
            Worker->>DB: SELECT * FROM orders WHERE checkout_id=...
            DB-->>Worker: Return Order A
            Worker-->>Runner: Return Order A (Idempotent)
        end
    end
```

---

## 3. Mutation Race Sequence (Optimistic Concurrency)

Shows how Versioning (OCC) detects dirty reads when an "Add Item" request interleaves with a "Payment" request.

```mermaid
sequenceDiagram
    participant User as User (Payment)
    participant Hacker as Attacker (Add Item)
    participant App as Checkout Service
    participant DB as SQLite DB

    note over User, DB: Scenario: Mutation Race (Optimistic Concurrency)

    User->>App: POST /pay (Total: $100)
    App->>DB: READ Cart (Version: 1)
    
    note over App, Hacker: Race Window Starts
    
    Hacker->>App: POST /add-item (Price: $50)
    App->>DB: UPDATE Cart (Total: $150, Version: 2)
    DB-->>App: Success
    
    note over App, Hacker: Cart is now Version 2
    
    App->>DB: CREATE Order (Expect Version: 1)
    
    rect rgb(255, 230, 230)
        note right of App: Validation Logic
        DB->>DB: Check: Current Version (2) != Expected (1)
    end
    
    DB--xApp: Error: StateConflict / Version Mismatch
    App--xUser: 409 Conflict: Cart Modified, Please Retry
    
    note right of DB: Integrity Preserved:<br/>Payment Rejected due to<br/>stale view of cart.
```

---

## 4. Payment Integrity Guard Logic (Flowchart)

The decision tree for handling incoming requests safely.

```mermaid
flowchart TD
    Start([User Agent Sends 'Complete Checkout']) --> CheckIdem{"Check In-Memory<br/>Idempotency Key?"}
    
    CheckIdem -- "Not Found" --> AttemptCreate["Attempt Atomic Insert<br/>WHERE version = expected"]
    
    AttemptCreate --> CheckResult{"DB Result?"}
    
    CheckResult -- "Success" --> UpdateStatus["Update Checkout Status"]
    UpdateStatus --> StoreResponse["Store in Cache"]
    StoreResponse --> ReturnSuccess([Return Success])
    
    %% The New Path for Mutation Race
    CheckResult -- "Version Mismatch" --> Conflict["Return 409 Conflict<br/>(State Changed)"]
    Conflict --> ReturnError([Client Must Retry])
    
    CheckResult -- "Unique Constraint" --> CatchError["Catch DuplicateOrderError"]
    CatchError --> FetchExisting["Fetch Existing Order"]
    FetchExisting --> ReturnExisting["Return Existing Order"]
    
    ReturnExisting --> ReturnSuccess
    CheckIdem -- "Found" --> ReturnCached["Return Cached"]
    ReturnCached --> ReturnSuccess
```

---

## 5. State Diagram (Order Lifecycle)

Formalizing the idempotent state transition: "Failure to Create" is a valid path to "Success".

```mermaid
stateDiagram
  direction TB
  state FetchExisting {
    direction TB
    [*] --> LookupOrder
    LookupOrder --> ReturnOrder
[*]    LookupOrder
    ReturnOrder
  }
  [*] --> CheckoutPending
  CheckoutPending --> Race:Complete Checkout
  Race --> OrderCreated:Insert Success (Winner)
  Race --> FetchExisting:Insert Failed (Unique Violation)
  FetchExisting --> OrderCreated:Return Existing Order
  OrderCreated --> [*]
  note right of Race 
  Guarded by DB Unique Constraint
        on checkout_id
  end note
```

---

## 6. Conflict Recovery After OCC Rejection

Shows the post-conflict path after a stale write is rejected: the payment attempt arrives with an expected checkout version, the persistence layer detects that storage has advanced, the write fails with a conflict, and the caller must refetch current state before retrying or asking for reconfirmation.

```mermaid
sequenceDiagram
    participant Agent as Agent / Client
    participant API as Checkout Service
    participant DB as Persistence Layer
    participant User as User / Upstream Workflow

    Agent->>API: Complete checkout(checkout_id, expected_version = n)
    API->>DB: create_order_safe(checkout_id, expected_version = n)
    DB->>DB: Re-read checkout version and total

    alt State still matches version n
        DB-->>API: Commit order
        API-->>Agent: Success, return committed order
    else State changed to version n+1
        DB-->>API: 409 StateConflictError
        API-->>Agent: Conflict, latest version = n+1
        Agent->>DB: Refetch latest checkout state

        alt Updated state still acceptable
            Agent->>API: Retry complete checkout(expected_version = n+1)
        else Approval required
            Agent->>User: Ask for reconfirmation
        end
    end

```
