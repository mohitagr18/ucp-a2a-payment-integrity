import asyncio
import uuid
import time
import httpx
import argparse
from app.ucp.constants import DATAPART_CHECKOUT_KEY, PAYMENT_DATA_KEY
from experiments.metrics import CSVWriter, ExperimentResult

# Configuration
BASE_URL = "http://localhost:8000"
CSV_FILE = "paper_results.csv"

async def setup_checkout(client, context_id):
    """Helper to create a cart and add one item."""
    # 1. Create
    resp = await client.post("/a2a", json={
        "kind": "message", "role": "user", "messageId": f"setup_{uuid.uuid4()}", "contextId": context_id,
        "parts": [{"kind": "data", "data": {"action": "create_checkout"}}]
    })
    cid = resp.json()["parts"][0]["data"][DATAPART_CHECKOUT_KEY]["checkout_id"]
    
    # 2. Add Item
    await client.post("/a2a", json={
        "kind": "message", "role": "user", "messageId": f"add_{uuid.uuid4()}", "contextId": context_id,
        "parts": [{"kind": "data", "data": {"action": "add_to_checkout", "checkout_id": cid, "product_id": "p1", "quantity": 1}}]
    })
    return cid

async def run_retry_storm(n_retries: int, mode_label: str):
    """
    Scenario 1: Retry Storm
    Sends the EXACT SAME payment message N times.
    """
    run_id = str(uuid.uuid4())[:8]
    print(f"[{run_id}] Starting Retry Storm (N={n_retries}, Mode={mode_label})...")
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        context_id = f"ctx_{run_id}"
        cid = await setup_checkout(client, context_id)
        
        # Prepare the SINGLE payment message
        payment_msg_id = f"pay_{run_id}"
        payload = {
            "kind": "message", "role": "user", "messageId": payment_msg_id, "contextId": context_id,
            "parts": [
                {"kind": "data", "data": {"action": "complete_checkout", "checkout_id": cid}},
                {"kind": "data", "data": {PAYMENT_DATA_KEY: {"fake": "token"}}}
            ]
        }

        # Fire requests concurrently
        start_time = time.time()
        tasks = [client.post("/a2a", json=payload) for _ in range(n_retries)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        duration = (time.time() - start_time) * 1000

        # Analyze
        order_ids = set()
        errors = 0
        for r in responses:
            if isinstance(r, Exception) or r.status_code != 200:
                errors += 1
                continue
            
            data = r.json()["parts"][0]["data"].get(DATAPART_CHECKOUT_KEY)
            if data and data.get("order_id"):
                order_ids.add(data["order_id"])

        violation = len(order_ids) > 1
        
        result = ExperimentResult(
            run_id=run_id,
            scenario="retry_storm",
            mode=mode_label,
            total_requests=n_retries,
            success_count=len(responses) - errors,
            failure_count=errors,
            integrity_violation=violation,
            duration_ms=duration,
            notes=f"Unique Orders: {len(order_ids)}"
        )
        return result

async def run_race_condition(n_workers: int, mode_label: str):
    """
    Scenario 2: Concurrent Race
    N distinct requests try to complete the same checkout simultaneously.
    """
    run_id = str(uuid.uuid4())[:8]
    print(f"[{run_id}] Starting Race Condition (N={n_workers}, Mode={mode_label})...")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        context_id = f"ctx_{run_id}"
        cid = await setup_checkout(client, context_id)

        start_time = time.time()
        tasks = []
        for i in range(n_workers):
            # DISTINCT message IDs
            payload = {
                "kind": "message", "role": "user", "messageId": f"race_{run_id}_{i}", "contextId": context_id,
                "parts": [
                    {"kind": "data", "data": {"action": "complete_checkout", "checkout_id": cid}},
                    {"kind": "data", "data": {PAYMENT_DATA_KEY: {"fake": "token"}}}
                ]
            }
            tasks.append(client.post("/a2a", json=payload))

        responses = await asyncio.gather(*tasks, return_exceptions=True)
        duration = (time.time() - start_time) * 1000

        # Analyze
        order_ids = set()
        for r in responses:
            if not isinstance(r, Exception) and r.status_code == 200:
                data = r.json()["parts"][0]["data"].get(DATAPART_CHECKOUT_KEY)
                if data and data.get("order_id"):
                    order_ids.add(data["order_id"])

        violation = len(order_ids) > 1

        result = ExperimentResult(
            run_id=run_id,
            scenario="concurrent_race",
            mode=mode_label,
            total_requests=n_workers,
            success_count=len(responses),
            failure_count=0,
            integrity_violation=violation,
            duration_ms=duration,
            notes=f"Unique Orders: {len(order_ids)}"
        )
        return result

async def run_mutation_race(n_pairs: int, mode_label: str):
    """
    Scenario 3: The 'Sneaky Add'
    Fires 'Complete Checkout' and 'Add Item' simultaneously.
    Success Criteria: The final total must match the paid total.
    """
    run_id = str(uuid.uuid4())[:8]
    print(f"[{run_id}] Starting Mutation Race (N={n_pairs}, Mode={mode_label})...")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        context_id = f"ctx_{run_id}"
        
        violations = 0
        
        # Run N separate race pairs
        for i in range(n_pairs):
            pair_ctx = f"{context_id}_{i}"
            # Setup: Cart with 1 item ($20)
            cid = await setup_checkout(client, pair_ctx) 
            
            # Fire both at once
            task_pay = client.post("/a2a", json={
                "kind": "message", "role": "user", "messageId": f"pay_{i}", "contextId": pair_ctx,
                "parts": [{"kind": "data", "data": {"action": "complete_checkout", "checkout_id": cid, PAYMENT_DATA_KEY: {"fake": "token"}}}]
            })
            
            task_add = client.post("/a2a", json={
                "kind": "message", "role": "user", "messageId": f"add_{i}", "contextId": pair_ctx,
                "parts": [{"kind": "data", "data": {"action": "add_to_checkout", "checkout_id": cid, "product_id": "p1", "quantity": 1}}]
            })
            
            res_pay, res_add = await asyncio.gather(task_pay, task_add, return_exceptions=True)
            
            if isinstance(res_pay, Exception) or res_pay.status_code != 200:
                continue # Skip if payment failed completely

            pay_data = res_pay.json()["parts"][0]["data"].get(DATAPART_CHECKOUT_KEY)
            
            # If payment succeeded (created an order)
            if pay_data and pay_data.get("order_id"):
                paid_total = pay_data["total_cents"]
                
                # Check final state of the cart
                # We expect either:
                # A) Payment won first -> Status is COMPLETED, Add failed/ignored -> Final Total == Paid Total ($20)
                # B) Add won first -> Total became $40, then Payment happened -> Paid Total == Final Total ($40)
                
                # Violation: We Paid $20, but final state is $40 (Item sneaked in)
                
                # Fetch fresh state
                final = await client.post("/a2a", json={
                    "kind": "message", "role": "user", "messageId": f"verify_{i}", "contextId": pair_ctx,
                    "parts": [{"kind": "data", "data": {"action": "add_to_checkout", "checkout_id": cid, "product_id": "p1", "quantity": 0}}]
                })
                final_data = final.json()["parts"][0]["data"].get(DATAPART_CHECKOUT_KEY)
                
                if final_data["total_cents"] != paid_total:
                    violations += 1
            
        result = ExperimentResult(
            run_id=run_id,
            scenario="mutation_race",
            mode=mode_label,
            total_requests=n_pairs * 2,
            success_count=(n_pairs * 2),
            failure_count=0,
            integrity_violation=(violations > 0),
            duration_ms=0, # Not tracking duration for this loop
            notes=f"Inconsistent States: {violations}"
        )
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--storm", type=int, default=50)
    parser.add_argument("--race", type=int, default=10)
    parser.add_argument("--mode", type=str, default="hardened", help="Label for CSV (baseline/hardened)")
    args = parser.parse_args()

    writer = CSVWriter(CSV_FILE)
    
    print(f"Running Experiments -> {CSV_FILE} [Mode: {args.mode}]")
    
    # 1. Storm
    res1 = asyncio.run(run_retry_storm(args.storm, args.mode))
    writer.write(res1)
    print(f" > Storm Result: Violation={res1.integrity_violation}")

    # 2. Race
    res2 = asyncio.run(run_race_condition(args.race, args.mode))
    writer.write(res2)
    print(f" > Race Result:  Violation={res2.integrity_violation}")
    
    # 3. Mutation (New) - Use 'race' count for N pairs
    res3 = asyncio.run(run_mutation_race(args.race, args.mode))
    writer.write(res3)
    print(f" > Mutation Result: Violation={res3.integrity_violation}, {res3.notes}")

if __name__ == "__main__":
    main()
