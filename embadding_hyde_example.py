from openai import OpenAI

GROQ_API_KEY = "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"

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)

def hyde(query: str) -> str:
    r = client.chat.completions.create(
        model="qwen/qwen3.8-27b",
        temperature=0.3,
        max_tokens=150,
        messages=[{
            "role": "user",
            "content": (
                "Write a short passage, in the register of an internal corporate "
                "policy document, that would directly answer this question. "
                "Invent plausible specifics. Do not hedge.\n\n"
                f"Question: {query}"
            ),
        }],
    )
    return r.choices[0].message.content.strip()

q = "How long do employees have to submit expense claims?"
print(hyde(q))
# Embed the output of hyde(q) instead of q, and search with that vector.
