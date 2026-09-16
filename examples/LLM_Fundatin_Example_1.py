import tiktoken

enc = tiktoken.get_encoding("o200k_base")

samples = [
    "orchestration",
    "The invoice total is $1,240.55.",
    "SELECT customer_id FROM orders WHERE status = 'PENDING';",
    "ପ୍ରତିଷ୍ଠାନ",
    "550e8400-e29b-41d4-a716-446655440000",
]

for s in samples:
    ids = enc.encode(s)
    pieces = [enc.decode([i]) for i in ids]
    print(f"{len(ids):>3} tokens | {s[:45]!r}")
    print(f"      {pieces}\n")