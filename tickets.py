"""
Command-line CRUD for support tickets.

Examples:
  python tickets.py create --title "VPN drops every hour" --category Network --priority High --customer "Aoife Ryan" --email aoife@example.com
  python tickets.py list --status Open --priority High
  python tickets.py show TCK-000042
  python tickets.py status TCK-000042 "In Progress"
  python tickets.py note TCK-000042 --author Rishi --text "Asked customer for router logs"
  python tickets.py delete TCK-000042
"""
import argparse
from datetime import datetime, timezone

from pymongo import ReturnDocument

from db import CATEGORIES, PRIORITIES, STATUSES, ensure_base_indexes, get_collection


def now():
    return datetime.now(timezone.utc)


def next_ticket_ref(tickets):
    """Build the next human-readable ID, e.g. TCK-000123.

    Good enough for a single-user demo. In a busy multi-user system you'd use
    an atomic counter document ($inc) to avoid two users getting the same number.
    """
    last = tickets.find_one({}, sort=[("ticket_ref", -1)], projection={"ticket_ref": 1})
    n = int(last["ticket_ref"].split("-")[1]) + 1 if last else 1
    return f"TCK-{n:06d}"


# ---------- Create ----------
def create_ticket(tickets, title, description, category, priority, customer, email, assigned_to=None):
    ticket = {
        "ticket_ref": next_ticket_ref(tickets),
        "title": title,
        "description": description,
        # Embedded sub-document: customer details always travel with the ticket.
        "customer": {"name": customer, "email": email},
        "category": category,
        "priority": priority,
        "status": "Open",
        "assigned_to": assigned_to,
        "created_at": now(),
        "updated_at": now(),
        "resolved_at": None,
        # Embedded array: notes belong to exactly one ticket, so they live inside it.
        # In SQL this would be a separate notes table joined on ticket_id.
        "notes": [],
    }
    tickets.insert_one(ticket)
    return ticket["ticket_ref"]


# ---------- Read ----------
def list_tickets(tickets, status=None, priority=None, category=None, limit=20):
    query = {}
    if status:
        query["status"] = status
    if priority:
        query["priority"] = priority
    if category:
        query["category"] = category
    # Projection: only fetch the fields the list view actually needs.
    fields = {"_id": 0, "ticket_ref": 1, "title": 1, "status": 1, "priority": 1, "category": 1, "created_at": 1}
    return list(tickets.find(query, fields).sort("created_at", -1).limit(limit))


def get_ticket(tickets, ref):
    return tickets.find_one({"ticket_ref": ref}, {"_id": 0})


# ---------- Update ----------
def update_status(tickets, ref, status):
    changes = {"status": status, "updated_at": now()}
    if status in ("Resolved", "Closed"):
        changes["resolved_at"] = now()
    else:
        changes["resolved_at"] = None  # reopened
    return tickets.find_one_and_update(
        {"ticket_ref": ref}, {"$set": changes}, return_document=ReturnDocument.AFTER
    )


def add_note(tickets, ref, author, text):
    # $push appends to the embedded array in a single atomic write.
    result = tickets.update_one(
        {"ticket_ref": ref},
        {"$push": {"notes": {"author": author, "text": text, "created_at": now()}},
         "$set": {"updated_at": now()}},
    )
    return result.matched_count == 1


# ---------- Delete ----------
def delete_ticket(tickets, ref):
    return tickets.delete_one({"ticket_ref": ref}).deleted_count == 1


# ---------- CLI ----------
def fmt_date(d):
    return d.strftime("%Y-%m-%d %H:%M") if d else "-"


def main():
    p = argparse.ArgumentParser(description="Support ticket tracker (MongoDB)")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create")
    c.add_argument("--title", required=True)
    c.add_argument("--description", default="")
    c.add_argument("--category", required=True, choices=CATEGORIES)
    c.add_argument("--priority", required=True, choices=PRIORITIES)
    c.add_argument("--customer", required=True)
    c.add_argument("--email", required=True)
    c.add_argument("--assigned-to")

    l = sub.add_parser("list")
    l.add_argument("--status", choices=STATUSES)
    l.add_argument("--priority", choices=PRIORITIES)
    l.add_argument("--category", choices=CATEGORIES)
    l.add_argument("--limit", type=int, default=20)

    s = sub.add_parser("show")
    s.add_argument("ref")

    u = sub.add_parser("status")
    u.add_argument("ref")
    u.add_argument("status", choices=STATUSES)

    n = sub.add_parser("note")
    n.add_argument("ref")
    n.add_argument("--author", required=True)
    n.add_argument("--text", required=True)

    d = sub.add_parser("delete")
    d.add_argument("ref")

    args = p.parse_args()
    tickets = get_collection()
    ensure_base_indexes(tickets)

    if args.cmd == "create":
        ref = create_ticket(tickets, args.title, args.description, args.category,
                            args.priority, args.customer, args.email, args.assigned_to)
        print(f"Created {ref}")

    elif args.cmd == "list":
        rows = list_tickets(tickets, args.status, args.priority, args.category, args.limit)
        if not rows:
            print("No tickets match.")
        for t in rows:
            print(f"{t['ticket_ref']}  {t['status']:<11} {t['priority']:<8} {t['category']:<9} "
                  f"{fmt_date(t['created_at'])}  {t['title']}")

    elif args.cmd == "show":
        t = get_ticket(tickets, args.ref)
        if not t:
            print("Ticket not found.")
            return
        print(f"{t['ticket_ref']}: {t['title']}")
        print(f"  Status: {t['status']} | Priority: {t['priority']} | Category: {t['category']}")
        print(f"  Customer: {t['customer']['name']} <{t['customer']['email']}>")
        print(f"  Assigned to: {t.get('assigned_to') or '-'}")
        print(f"  Created: {fmt_date(t['created_at'])} | Resolved: {fmt_date(t.get('resolved_at'))}")
        if t.get("description"):
            print(f"  Description: {t['description']}")
        print(f"  Notes ({len(t['notes'])}):")
        for note in t["notes"]:
            print(f"    [{fmt_date(note['created_at'])}] {note['author']}: {note['text']}")

    elif args.cmd == "status":
        t = update_status(tickets, args.ref, args.status)
        print(f"{args.ref} is now {t['status']}" if t else "Ticket not found.")

    elif args.cmd == "note":
        print("Note added." if add_note(tickets, args.ref, args.author, args.text) else "Ticket not found.")

    elif args.cmd == "delete":
        print("Deleted." if delete_ticket(tickets, args.ref) else "Ticket not found.")


if __name__ == "__main__":
    main()
