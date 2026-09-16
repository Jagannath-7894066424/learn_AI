import os
from pathlib import Path

from dotenv import load_dotenv

# The key is read from the environment — never hardcode it in a tracked file.
# Put it in chatbot_be/.env (which is gitignored), or export GROQ_API_KEY.
load_dotenv(Path(__file__).resolve().parent.parent / "chatbot_be" / ".env")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise SystemExit("GROQ_API_KEY is not set. Add it to chatbot_be/.env or export it.")

from openai import OpenAI


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
