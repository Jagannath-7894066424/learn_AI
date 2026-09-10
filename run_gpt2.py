import sys
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

MODEL_ID = "openai-community/gpt2"


def main(prompt: str):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading model {MODEL_ID} on {device}...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID)
    model.to(device)

    inputs = tokenizer(prompt, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=64, do_sample=True, temperature=0.8)

    text = tokenizer.decode(outputs[0], skip_special_tokens=True)
    print("\n=== Generated ===\n")
    print(text)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    else:
        prompt = "Hello, my name is"
    main(prompt)
