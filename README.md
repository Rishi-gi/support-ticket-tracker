# Support Ticket Tracker (MongoDB Atlas + Python)

A small IT support ticketing tool built to learn how a document database differs from the relational databases I'd used before. It covers CRUD operations, schema design with embedded documents, compound indexing measured with `explain()`, and reporting with the aggregation pipeline.

## Why I built it
I've worked in high-volume technical support, where tickets, their notes and their resolution times are the core data. I'd only used SQL, so I wanted to understand when a document model is a better fit, and to measure what indexing actually does rather than just read about it.

## Tech
MongoDB Atlas (free M0 cluster) · Python 3 · PyMongo · Faker · python-dotenv

## Data model
One `tickets` collection. Each ticket is a single document:

```json
{
  "ticket_ref": "TCK-000042",
  "title": "VPN keeps disconnecting",
  "customer": { "name": "Aoife Ryan", "email": "aoife@example.com" },
  "category": "Network",
  "priority": "High",
  "status": "In Progress",
  "assigned_to": "S. Walsh",
  "created_at": "2026-09-01T09:14:00Z",
  "resolved_at": null,
  "notes": [
    { "author": "S. Walsh", "text": "Asked customer for router logs", "created_at": "..." }
  ]
}
```

**Why embed notes instead of a separate collection?** Notes belong to exactly one ticket, are always read together with it, and a ticket only has a handful. Embedding means one read fetches everything, and adding a note is one atomic `$push`. In SQL this would be a `notes` table joined on `ticket_id`. I'd split notes out if a ticket could collect thousands of them, since a MongoDB document is capped at 16 MB.

## Indexing results
Query: open, High-priority, Network tickets, newest first, on a collection of **20,000** tickets.

| Metric | No index | Compound index |
|---|---|---|
| Docs returned | 124 | 124 |
| Docs examined | 20,000 | 124 |
| Keys examined | 0 | 124 |
| Plan | COLLSCAN + in-memory SORT | IXSCAN + FETCH (no sort needed) |

The index cut documents examined by about **161x**: MongoDB went from reading every ticket to reading only the 124 it returned. Query time also fell from 17 ms to 1 ms, but timings on a free M0 cluster are noisy, so documents examined is the reliable measure.

Index: `{ status: 1, priority: 1, category: 1, created_at: -1 }`

It follows the **ESR rule** (Equality, Sort, Range): exact-match fields first, then the sort field. Without it, MongoDB reads every document (COLLSCAN) and sorts results in memory. With it, MongoDB jumps straight to the matching entries, already in date order.

**Trade-off:** indexes speed up reads but slow down writes and use storage, because every insert must update them too. So I indexed the query that runs constantly, not every field.

## Reports (aggregation pipeline)
`reports.py` answers:
- Tickets per category, with how many are still open (`$group` + `$cond`)
- Average resolution time per priority (`$match` → `$project` → `$group`)
- Most active agents by notes written (`$unwind` on the embedded array)

## SQL vs MongoDB: when I'd choose each
I'd pick **MongoDB** when records are naturally self-contained and their shape varies, like a ticket with its notes. I'd pick **SQL** when data is highly related and needs joins across many tables, or strict multi-row transactions, like billing and payments. The schema flexibility cuts both ways: MongoDB won't stop you writing a misspelled status, so this app validates values itself.

## Security
- The connection string lives in `.env`, which is git-ignored. Only `.env.example` is committed.
- The Atlas database user has `readWrite` on the `support_tracker` database only, not admin rights (least privilege).
- Atlas Network Access is limited to my own IP address.
- All ticket data is fake, generated with Faker.

## Run it yourself
1. Create a free Atlas M0 cluster, a database user, and allow your IP under Network Access.
2. Set up the project:
   ```bash
   python -m venv .venv
   source .venv/bin/activate      # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env           # then paste your connection string into .env
   ```
3. Load data and run the demos:
   ```bash
   python seed.py --count 20000
   python index_demo.py
   python reports.py
   ```
4. Try the CLI:
   ```bash
   python tickets.py create --title "Printer offline" --category Hardware --priority Medium --customer "Test User" --email test@example.com
   python tickets.py list --status Open --priority High
   python tickets.py show TCK-000001
   python tickets.py note TCK-000001 --author Rishi --text "Restarted print spooler"
   python tickets.py status TCK-000001 Resolved
   ```

## What I'd add next
A small Flask API, MongoDB schema validation rules at the database level, and an atomic counter for ticket numbers so concurrent users can't collide.
