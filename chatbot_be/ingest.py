"""Ingest .txt / .md files into Postgres from the command line.

Usage:
    python ingest.py                 # ingest everything under ../docs
    python ingest.py a.md notes/     # ingest specific files and/or folders

The web UI does the same thing through POST /api/documents/upload.
"""

import logging
import sys
from pathlib import Path

import rag

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")


def collect_files(args) -> list[Path]:
    """Expand CLI arguments (or the default docs folder) into a file list."""
    targets = [Path(a) for a in args] if args else [rag.DOCS_DIR]
    files: list[Path] = []
    for target in targets:
        try:
            if target.is_dir():
                files.extend(p for p in sorted(target.rglob("*")) if p.suffix.lower() in rag.SUFFIXES)
            elif target.is_file() and target.suffix.lower() in rag.SUFFIXES:
                files.append(target)
            else:
                print(f"  ! skipping {target} (not a .txt/.md file or folder)")
        except OSError as exc:
            # An unreadable directory shouldn't abort the whole run.
            print(f"  ! skipping {target} ({exc})")
    return files


def main() -> int:
    try:
        rag.init_schema()
    except rag.RagError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    files = collect_files(sys.argv[1:])
    if not files:
        print(f"No .txt or .md files found in {rag.DOCS_DIR}. Add some, or pass paths as arguments.")
        return 1

    total, failed = 0, 0
    try:
        with rag.connect() as conn:
            for path in files:
                # Store a repo-relative source name when possible, so the CLI and the
                # web uploader label the same file identically.
                try:
                    source = str(path.resolve().relative_to(rag.ROOT_DIR))
                except ValueError:
                    source = str(path)

                try:
                    text = rag.extract_text(path.read_bytes(), path.name)
                except (OSError, rag.ExtractionError) as exc:
                    print(f"  ! {source}: {exc}")
                    failed += 1
                    continue

                try:
                    chunks = rag.store_document(conn, source, text)
                except rag.RagError as exc:
                    # Report and continue — one bad file shouldn't stop the batch.
                    print(f"  ! {source}: {exc}")
                    failed += 1
                    continue

                if chunks == 0:
                    print(f"  - {source}: empty, skipped")
                    continue
                total += chunks
                print(f"  + {source}: {chunks} chunks")
    except rag.RagError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130

    print(f"\nIngested {total} chunks from {len(files) - failed} file(s)."
          + (f" {failed} failed." if failed else ""))
    return 1 if failed and total == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
