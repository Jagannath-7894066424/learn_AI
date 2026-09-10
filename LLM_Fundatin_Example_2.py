import numpy as np

def softmax(x, axis=-1):
    x = x - x.max(axis=axis, keepdims=True)
    e = np.exp(x)
    return e / e.sum(axis=axis, keepdims=True)

def causal_self_attention(X, Wq, Wk, Wv):
    """X: (n, d_model). Returns (n, d_k) plus the attention matrix."""
    Q, K, V = X @ Wq, X @ Wk, X @ Wv
    d_k = K.shape[-1]
    scores = (Q @ K.T) / np.sqrt(d_k)

    n = X.shape[0]
    mask = np.triu(np.ones((n, n)), k=1).astype(bool)   # strictly upper = future
    scores = np.where(mask, -np.inf, scores)

    A = softmax(scores)
    return A @ V, A

rng = np.random.default_rng(0)
n, d_model, d_k = 6, 8, 4
X  = rng.normal(size=(n, d_model))
print("Input (X):")
print(X)
Wq = rng.normal(size=(d_model, d_k)) * 0.3
print("Query weights (Wq):")
print(Wq)
Wk = rng.normal(size=(d_model, d_k)) * 0.3
print("Key weights (Wk):")
print(Wk)
Wv = rng.normal(size=(d_model, d_k)) * 0.3
print(Wv)

out, A = causal_self_attention(X, Wq, Wk, Wv)
print("attention weights (rows sum to 1, upper triangle is 0):")
print(np.round(A, 3))
print("\noutput shape:", out.shape)