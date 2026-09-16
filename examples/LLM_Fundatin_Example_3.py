import os
from pathlib import Path

from dotenv import load_dotenv

# The key is read from the environment — never hardcode it in a tracked file.
# Put it in chatbot_be/.env (which is gitignored), or export GROQ_API_KEY.
load_dotenv(Path(__file__).resolve().parent.parent / "chatbot_be" / ".env")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise SystemExit("GROQ_API_KEY is not set. Add it to chatbot_be/.env or export it.")

# from openai import OpenAI


# client = OpenAI(
#     api_key="GROQ_API_KEY",              # or omit and set env var GROQ_API_KEY
#     base_url="https://api.groq.com/openai/v1/chat/completions",
# )


from openai import OpenAI


client = OpenAI(
    api_key=GROQ_API_KEY,                      # variable, no quotes
    base_url="https://api.groq.com/openai/v1",  # stop at /v1
)

prompt = "What is chat-gpt ?"

for temp in (0.0, 0.7, 1.3):
    outs = [
        client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            temperature=temp,
            max_tokens=40,
            messages=[{"role": "user", "content": prompt}],
        ).choices[0].message.content
        for _ in range(3)
    ]
    print(f"\n--- temperature={temp} ---")
    for o in outs:
        print(" •", o.strip().replace("\n", " ")[:110])
