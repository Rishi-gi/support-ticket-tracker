"""
Generate realistic fake tickets so indexing makes a measurable difference.

  python seed.py            # 20,000 tickets (default)
  python seed.py --count 50000 --reset
"""
import argparse
import random
from datetime import datetime, timedelta, timezone

from faker import Faker

from db import CATEGORIES, PRIORITIES, STATUSES, ensure_base_indexes, get_collection

fake = Faker("en_IE")

ISSUES = {
    "Network": ["VPN keeps disconnecting", "No internet after router reset", "Slow Wi-Fi in office", "Cannot reach shared drive"],
    "Billing": ["Charged twice this month", "Invoice missing", "Direct debit failed", "Refund not received"],
    "Hardware": ["Laptop won't power on", "Monitor flickering", "Printer offline", "Headset not detected"],
    "Software": ["Outlook crashes on start", "App update failed", "Teams audio not working", "License expired error"],
    "Account": ["Locked out after password reset", "MFA prompt not arriving", "Need access to finance folder", "Username change request"],
}
AGENTS = ["A. Byrne", "S. Walsh", "R. Kumar", "M. O'Sullivan", "J. Doyle"]

# Weighted so the data looks like a real queue: most tickets are closed,
# few are critical. That skew is what makes selective indexes matter.
STATUS_W = [0.15, 0.10, 0.25, 0.50]
PRIORITY_W = [0.35, 0.40, 0.20, 0.05]
# Typical hours to resolve, by priority.
RESOLVE_HOURS = {"Low": (24, 240), "Medium": (8, 96), "High": (2, 36), "Critical": (0.5, 12)}


def make_ticket(n):
    category = random.choice(CATEGORIES)
    priority = random.choices(PRIORITIES, PRIORITY_W)[0]
    status = random.choices(STATUSES, STATUS_W)[0]
    created = datetime.now(timezone.utc) - timedelta(minutes=random.randint(0, 365 * 24 * 60))
    resolved = None
    if status in ("Resolved", "Closed"):
        resolved = created + timedelta(hours=random.uniform(*RESOLVE_HOURS[priority]))

    notes = []
    for _ in range(random.randint(0, 4)):
        notes.append({
            "author": random.choice(AGENTS),
            "text": fake.sentence(nb_words=10),
            "created_at": created + timedelta(hours=random.uniform(0.1, 24)),
        })

    return {
        "ticket_ref": f"TCK-{n:06d}",
        "title": random.choice(ISSUES[category]),
        "description": fake.paragraph(nb_sentences=2),
        "customer": {"name": fake.name(), "email": fake.email()},
        "category": category,
        "priority": priority,
        "status": status,
        "assigned_to": None if status == "Open" else random.choice(AGENTS),
        "created_at": created,
        "updated_at": resolved or created,
        "resolved_at": resolved,
        "notes": sorted(notes, key=lambda x: x["created_at"]),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=20000)
    p.add_argument("--reset", action="store_true", help="delete all existing tickets first")
    args = p.parse_args()

    tickets = get_collection()
    if args.reset:
        tickets.drop()
        print("Collection dropped.")
    ensure_base_indexes(tickets)

    start = tickets.count_documents({}) + 1
    batch, batch_size = [], 1000
    for i in range(start, start + args.count):
        batch.append(make_ticket(i))
        if len(batch) == batch_size:
            tickets.insert_many(batch)  # one round trip per 1,000 docs instead of 1,000 round trips
            batch = []
            print(f"  inserted up to TCK-{i:06d}")
    if batch:
        tickets.insert_many(batch)
    print(f"Done. Collection now holds {tickets.count_documents({}):,} tickets.")


if __name__ == "__main__":
    main()
