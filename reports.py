"""
Aggregation pipeline reports: the MongoDB equivalent of SQL GROUP BY.

  python reports.py
"""
from db import get_collection

HOUR_MS = 1000 * 60 * 60


def tickets_by_category(tickets):
    """Total and open tickets per category, busiest first."""
    pipeline = [
        {"$group": {
            "_id": "$category",
            "total": {"$sum": 1},
            "open": {"$sum": {"$cond": [{"$in": ["$status", ["Open", "In Progress"]]}, 1, 0]}},
        }},
        {"$sort": {"total": -1}},
    ]
    return list(tickets.aggregate(pipeline))


def avg_resolution_by_priority(tickets):
    """Average hours from creation to resolution, per priority."""
    pipeline = [
        # 1. Only tickets that actually got resolved.
        {"$match": {"resolved_at": {"$ne": None}}},
        # 2. Work out each ticket's resolution time in hours.
        {"$project": {
            "priority": 1,
            "hours": {"$divide": [{"$subtract": ["$resolved_at", "$created_at"]}, HOUR_MS]},
        }},
        # 3. Group and average.
        {"$group": {
            "_id": "$priority",
            "avg_hours": {"$avg": "$hours"},
            "resolved": {"$sum": 1},
        }},
    ]
    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    return sorted(tickets.aggregate(pipeline), key=lambda r: order.get(r["_id"], 9))


def busiest_agents(tickets, limit=5):
    """Who has written the most notes. $unwind turns one ticket with 3 notes into 3 rows."""
    pipeline = [
        {"$unwind": "$notes"},
        {"$group": {"_id": "$notes.author", "notes_written": {"$sum": 1}}},
        {"$sort": {"notes_written": -1}},
        {"$limit": limit},
    ]
    return list(tickets.aggregate(pipeline))


def main():
    tickets = get_collection()

    print("\nTickets by category")
    print(f"{'Category':<12}{'Total':>8}{'Open':>8}")
    for r in tickets_by_category(tickets):
        print(f"{r['_id']:<12}{r['total']:>8,}{r['open']:>8,}")

    print("\nAverage resolution time by priority")
    print(f"{'Priority':<12}{'Avg hours':>10}{'Resolved':>10}")
    for r in avg_resolution_by_priority(tickets):
        print(f"{r['_id']:<12}{r['avg_hours']:>10.1f}{r['resolved']:>10,}")

    print("\nMost active agents (by notes written)")
    for r in busiest_agents(tickets):
        print(f"  {r['_id']:<16}{r['notes_written']:>6,}")


if __name__ == "__main__":
    main()
