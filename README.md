# run_gpt2 demo

This project includes a small runner to load `openai-community/gpt2` from the Hugging Face Hub and generate text.

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the demo:

```bash
python3 run_gpt2.py "Once upon a time"
```

Notes:
- The first run downloads the model from the Hub and may take a while.
- If you have a GPU and an appropriate PyTorch build, the script will use it automatically.
