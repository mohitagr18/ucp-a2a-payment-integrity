
# UCP Agent: Payment Integrity & Idempotency Experiment

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Protocol: A2A](https://img.shields.io/badge/Protocol-A2A_v1.0-green.svg)](https://a2a-protocol.org)
[![Protocol: UCP](https://img.shields.io/badge/Protocol-UCP_Checkout-orange.svg)](https://ucp.dev)
[![Status: Research Prototype](https://img.shields.io/badge/Status-Research_Prototype-red.svg)]()

A minimal, high-fidelity implementation of a **Universal Commerce Protocol (UCP)** Checkout Agent over **Agent-to-Agent (A2A)** messaging. 

This repository serves as the artifact for an academic study on **Payment Integrity in Agentic Commerce**. It demonstrates how "naive" agent implementations create critical double-spend and state-corruption vulnerabilities, and provides a hardened reference architecture using strict **Idempotency** and **Checkout-Level Locking**.

---

## 🔬 Research Scenarios & Results

We subjected the agent to three distinct concurrency stress tests (N=10 to N=200 requests) in both **Baseline (Naive)** and **Hardened** modes. The results, generated on Apple M2 hardware, are summarized below.

### 1. The "Retry Storm" (Network Duplication)
*   **Scenario:** A client (or network intermediary) sends the exact same `complete_checkout` message N times in rapid succession.
*   **Vulnerability:** Naive agents treat each message as a new intent, charging the user N times.
*   **Result:**
    *   **Baseline:** 100% Failure Rate. At N=200, **200 unique orders** were created for a single cart.
    *   **Hardened:** 0% Failure Rate. At N=200, **exactly 1 order** was created.
    *   **Performance:** Hardened mode was **3.1x faster** (232ms vs 739ms) because cached idempotent responses bypass expensive write operations.

### 2. The "Concurrent Race" (Parallel Payment)
*   **Scenario:** N distinct users (or devices) attempt to pay for the same shared cart at the exact same millisecond.
*   **Vulnerability:** Without locking, multiple threads read the "Unpaid" state simultaneously and proceed to capture funds.
*   **Result:**
    *   **Baseline:** 100% Failure Rate. Multiple winners in the race, leading to double-spending.
    *   **Hardened:** 0% Failure Rate. Transactional locks ensured strict serialization; only the first request succeeded.

### 3. The "Mutation Race" (The Sneaky Add)
*   **Scenario:** User A clicks "Pay" ($20) while User B clicks "Add Item" ($20) on the same cart simultaneously.
*   **Vulnerability:** "Dirty Reads." The payment logic reads $20, authorizes $20, but the Add logic commits $40. The order is marked "Paid" but the cart total ($40) mismatches the payment ($20).
*   **Result:**
    *   **Baseline:** High Failure Rate. At N=200 pairs (400 requests), **146 inconsistent states** were recorded (36% corruption rate).
    *   **Hardened:** 0% Failure Rate. **0 inconsistent states.** The lock forces operations to be sequential.

---

## 🏗 Architecture

The system mimics a real-world "Headless Merchant" agent:

*   **Protocol:** [Agent-to-Agent (A2A)](https://a2a-protocol.org) over JSON-RPC.
*   **Binding:** [UCP Checkout](https://ucp.dev).
*   **Runtime:** Python FastAPI + Uvicorn (ASGI).
*   **Persistence:** SQLite (File-based) with strict transactional isolation.
*   **Logic:** 
    *   **Baseline Mode:** Naive implementation (vulnerable).
    *   **Hardened Mode:** Uses `IdempotencyStore` (caches responses by `messageId`) and `LockManager` (mutex per `checkout_id`).

### Key Components

| Component | Responsibility | Phase Implemented |
| :--- | :--- | :--- |
| `app/routes/a2a_rpc.py` | A2A Protocol Endpoint & Dispatcher | Phase 1 |
| `app/infra/store.py` | SQLite persistence for Checkouts/Orders | Phase 3 |
| `app/infra/idempotency.py` | Caches A2A responses to prevent re-processing | Phase 2 |
| `app/infra/lock_manager.py` | Handles concurrency locking for carts | Phase 2 |
| `experiments/runner.py` | CLI harness for Retry Storms & Races | Phase 4 |

---

## 🚀 Getting Started

### Prerequisites

*   **Python 3.11+**
*   **[uv](https://github.com/astral-sh/uv)** (Recommended for fast dependency management)

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/your-username/ucp-a2a-payment-integrity.git
cd ucp-a2a-payment-integrity

# Sync dependencies (creates virtualenv automatically)
uv sync
```

### 2. Run the Agent (Hardened Mode)

```bash
uv run uvicorn app.main:create_app --port 8000
```

*   The agent is now listening on `http://localhost:8000/a2a`.
*   Discovery endpoint: `http://localhost:8000/.well-known/ucp`.

### 3. Verify Functionality (Demo)

Run the interactive console chat to simulate a user buying a product:

```bash
uv run python demo.py
```

---

## 🧪 Reproducing Experiments

This repository includes a deterministic experiment runner to generate the data for the paper.

### Experiment 1: Baseline Failure (Vulnerability Demonstration)

Run the server in **UNSAFE** mode to disable locks and idempotency checks.

1.  **Start Server (Unsafe):**
    ```bash
    SAFETY_MODE=off uv run uvicorn app.main:create_app --port 8000
    ```

2.  **Run Experiment:**
    ```bash
    uv run python -m experiments.runner --storm 50 --race 50 --mode baseline
    ```

3.  **Result:** Check `paper_results.csv`. You should see `integrity_violation=True`.

### Experiment 2: Hardened Success (Solution Verification)

Run the server in default **SAFE** mode.

1.  **Start Server (Safe):**
    ```bash
    # (Ctrl+C previous server)
    uv run uvicorn app.main:create_app --port 8000
    ```

2.  **Run Experiment:**
    ```bash
    uv run python -m experiments.runner --storm 50 --race 50 --mode hardened
    ```

3.  **Result:** Check `paper_results.csv`. You should see `integrity_violation=False`.

---

## 🛠 Project Structure

```text
.
├── app
│   ├── a2a          # Protocol schemas & message dispatcher
│   ├── domain       # Core business logic (Checkout, Order, Product)
│   ├── infra        # Persistence (SQLite), Locks, Idempotency
│   ├── routes       # FastAPI endpoints
│   ├── services     # Application services (CheckoutService)
│   └── ucp          # UCP specific constants & models
├── experiments      # Paper experiment harness
│   ├── metrics.py   # CSV logging
│   └── runner.py    # Main CLI runner
├── tests            # Pytest suite
│   ├── test_a2a_checkout_basics.py      # Phase 1: Functionality
│   ├── test_p2_idempotency_hardened.py  # Phase 2: Safety logic
│   └── test_p3_persistence.py           # Phase 3: Data survival
├── demo.py          # Interactive console chat
└── pyproject.toml   # Dependencies & config
```

## 📜 License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.

## 🔗 References

*   [Universal Commerce Protocol (UCP)](https://ucp.dev)
*   [Agent-to-Agent Protocol Specification](https://a2a-protocol.org)
