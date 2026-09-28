"""
Measure a real query before and after adding a compound index.

The query is the one a support team lead runs all day:
  "Show me open High-priority Network tickets, newest first."

Run:  python index_demo.py
Copy the printed table into the README.
"""
from db import get_db

INDEX_NAME = "status_priority_category_created"
FILTER = {"status": "Open", "priority": "High", "category": "Network"}
SORT = {"created_at": -1}


def collect_stages(plan, found=None):
    """Walk the (nested) winning plan and list its stage names, e.g. ['FETCH', 'IXSCAN']."""
    found = [] if found is None else found
    if isinstance(plan, dict):
        if "stage" in plan:
            found.append(plan["stage"])
        for v in plan.values():
            collect_stages(v, found)
    elif isinstance(plan, list):
        for item in plan:
            collect_stages(item, found)
    return found


def explain(db):
    result = db.command(
        "explain",
        {"find": "tickets", "filter": FILTER, "sort": SORT},
        verbosity="executionStats",
    )
    stats = result["executionStats"]
    plan = result["queryPlanner"]["winningPlan"]
    return {
        "returned": stats["nReturned"],
        "docs_examined": stats["totalDocsExamined"],
        "keys_examined": stats["totalKeysExamined"],
        "time_ms": stats["executionTimeMillis"],
        "stages": " -> ".join(dict.fromkeys(collect_stages(plan))),
    }


def main():
    db = get_db()
    tickets = db["tickets"]
    total = tickets.count_documents({})
    if total == 0:
        print("No data yet. Run: python seed.py")
        return

    # Start clean so "before" really means no helpful index.
    if INDEX_NAME in tickets.index_information():
        tickets.drop_index(INDEX_NAME)

    before = explain(db)

    # ESR rule: Equality fields first (status, priority, category),
    # then the Sort field (created_at). This lets MongoDB jump straight to the
    # matching tickets AND read them already in date order, so no in-memory sort.
    tickets.create_index(
        [("status", 1), ("priority", 1), ("category", 1), ("created_at", -1)],
        name=INDEX_NAME,
    )
    after = explain(db)

    print(f"\nCollection size: {total:,} tickets")
    print(f"Query: {FILTER}, sorted by created_at desc\n")
    print(f"{'Metric':<18}{'No index':>20}{'Compound index':>20}")
    print("-" * 58)
    for key, label in [("returned", "Docs returned"), ("docs_examined", "Docs examined"),
                       ("keys_examined", "Keys examined"), ("time_ms", "Time (ms)")]:
        print(f"{label:<18}{before[key]:>20,}{after[key]:>20,}")
    print(f"\nPlan before: {before['stages']}")
    print(f"Plan after:  {after['stages']}")

    if after["returned"]:
        ratio = before["docs_examined"] / max(after["docs_examined"], 1)
        print(f"\nThe index cut documents examined by about {ratio:,.0f}x.")
    print("\nNote: time_ms on a free M0 cluster is noisy. 'Docs examined' is the reliable number.")


if __name__ == "__main__":
    main()
