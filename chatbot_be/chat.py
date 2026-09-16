"""Terminal RAG chat — the command-line equivalent of the web UI.

Usage:
    python chat.py
"""

import logging
import sys

import rag

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")


def answer_once(conn, question: str) -> None:
    """Retrieve and answer one question, reporting failures without exiting."""
    try:
        rows = rag.retrieve(conn, question)
    except rag.RagError as exc:
        print(f"\n! Search failed: {exc}\n")
        return

    if not rows:
        print("\nBot: I don't know based on the provided documents.\n")
        return

    try:
        answer = rag.llm_answer(question, rag.build_context(rows))
    except rag.ConfigError as exc:
        print(f"\n! Configuration problem: {exc}\n")
        return
    except rag.RagError as exc:
        print(f"\n! The model could not answer: {exc}\n")
        return

    print(f"\nBot: {answer}")
    print(f"     [sources: {', '.join(sorted({src for _c, src, _d in rows}))}]\n")


def main() -> int:
    try:
        rag.init_schema()
    except rag.RagError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    model = rag.GROQ_MODEL if rag.LLM_PROVIDER == "groq" else rag.OLLAMA_MODEL
    print(f"RAG chat — provider: {rag.LLM_PROVIDER} ({model})")
    print("Ask a question, or type 'exit' to quit.\n")

    try:
        with rag.connect() as conn:
            try:
                count = rag.count_chunks(conn)
            except rag.RagError as exc:
                print(f"! Could not count indexed chunks: {exc}\n")
                count = 0
            print("The documents table is empty — run `python ingest.py` first.\n" if count == 0
                  else f"{count} chunks indexed.\n")

            while True:
                try:
                    question = input("You: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break

                if not question:
                    continue
                if question.lower() in {"exit", "quit", ":q"}:
                    break

                answer_once(conn, question)
    except rag.RagError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("Bye.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
