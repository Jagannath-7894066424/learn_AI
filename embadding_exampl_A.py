import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel

MODEL = "sentence-transformers/all-MiniLM-L6-v2"

texts = [
    "What is our refund window?",
    "Customers may return goods within 30 days of delivery.",
    "Customers may not return goods after delivery.",
    "Invoice INV-88214 is overdue.",
    "Invoice INV-88215 is overdue.",
    "The quarterly revenue forecast was revised upward.",
]

tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModel.from_pretrained(MODEL)
model.eval()

batch = tok(texts, padding=True, truncation=True, return_tensors="pt")
with torch.no_grad():
    hidden = model(**batch).last_hidden_state       # (n, tokens, d)

mask = batch["attention_mask"].unsqueeze(-1).float()
E = (hidden * mask).sum(1) / mask.sum(1)            # mean-pool over real tokens
E = E.numpy()
E = E / np.linalg.norm(E, axis=1, keepdims=True)    # normalise, then dot == cosine

S = E @ E.T
np.set_printoptions(precision=3, suppress=True)
print(S)

print("\nquestion vs affirmative answer:", round(float(S[0, 1]), 3))
print("question vs negated answer:   ", round(float(S[0, 2]), 3))
print("INV-88214 vs INV-88215:       ", round(float(S[3, 4]), 3))
