# from openai import OpenAI


# GROQ_API_KEY = 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
# client = OpenAI(
#     api_key="GROQ_API_KEY",              # or omit and set env var GROQ_API_KEY
#     base_url="https://api.groq.com/openai/v1/chat/completions",
# )


from openai import OpenAI

GROQ_API_KEY = "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"   # your key, in quotes

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
