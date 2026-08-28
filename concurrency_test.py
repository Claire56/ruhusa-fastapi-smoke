import asyncio

import httpx


BASE_URL = "http://127.0.0.1:8000"
CALLERS = 20


async def main():
    async with httpx.AsyncClient(timeout=30.0) as client:
        prepare = await client.post(
            f"{BASE_URL}/concurrency/prepare",
            json={
                "account_id": "concurrency-test",
                "amount": 100,
                "principal_id": "billing-agent",
            },
        )
        prepare.raise_for_status()

        invocation_id = prepare.json()["invocation_id"]

        print(f"Invocation: {invocation_id}")
        print(f"Launching {CALLERS} concurrent callers...")

        async def compete(worker_id: int):
            response = await client.post(
                f"{BASE_URL}/concurrency/{invocation_id}",
                json={
                    "account_id": "concurrency-test",
                    "amount": 100,
                    "principal_id": "billing-agent",
                },
            )

            return worker_id, response.status_code, response.json()

        results = await asyncio.gather(
            *(compete(i) for i in range(1, CALLERS + 1))
        )

        winners = []
        blocked = []

        for worker_id, status, body in results:
            if body.get("winner"):
                winners.append((worker_id, status, body))
            else:
                blocked.append((worker_id, status, body))

        print()
        print("RESULT")
        print(f"Total callers: {len(results)}")
        print(f"Winners:       {len(winners)}")
        print(f"Blocked:       {len(blocked)}")

        if winners:
            winner_id, status, body = winners[0]
            print()
            print(f"Winner worker: {winner_id}")
            print(f"Claim ID:      {body.get('claim_id')}")
            print(f"Attempt:       {body.get('attempt')}")
            print(f"Final state:   {body.get('state')}")

        execution = await client.get(
            f"{BASE_URL}/executions/{invocation_id}"
        )

        print()
        print("FINAL EXECUTION RECORD")
        print(execution.json())

        refunds = await client.get(f"{BASE_URL}/refunds")
        matching = [
            item
            for item in refunds.json()["items"]
            if item["invocation_id"] == invocation_id
        ]

        print()
        print(f"Side effects for invocation: {len(matching)}")

        assert len(winners) == 1, (
            f"SECURITY FAILURE: expected 1 winner, got {len(winners)}"
        )
        assert len(blocked) == CALLERS - 1
        assert execution.json()["state"] == "completed"
        assert execution.json()["attempt_count"] == 1
        assert len(matching) == 1, (
            f"SECURITY FAILURE: expected 1 side effect, got {len(matching)}"
        )

        print()
        print("PASS: exactly one caller obtained execution authority.")


if __name__ == "__main__":
    asyncio.run(main())