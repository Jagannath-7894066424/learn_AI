from dataclasses import dataclass, asdict
import tiktoken

enc = tiktoken.get_encoding("o200k_base")

@dataclass
class Chunk:
    text: str          # raw text, shown to the user
    embed_text: str    # what actually gets embedded
    doc_id: str
    breadcrumb: str
    token_count: int

def chunk_section(doc_id: str, breadcrumb: str, body: str,
                  target=600, overlap=80) -> list[Chunk]:
    ids = enc.encode(body)
    out, start = [], 0
    while start < len(ids):
        window = ids[start : start + target]
        text = enc.decode(window)
        out.append(Chunk(
            text=text,
            embed_text=f"[{breadcrumb}]\n{text}",   # <-- the trick
            doc_id=doc_id,
            breadcrumb=breadcrumb,
            token_count=len(window),
        ))
        if start + target >= len(ids):
            break
        start += target - overlap
    return out

chunks = chunk_section(
    "MSA-2024-11",
    "MSA-2024-11 › §7 Limitation of Liability › 7.3 Consequential Damages",
    "Neither party shall be liable for indirect, incidental, or consequential "
    "damages arising out of or relating to this Agreement, whether in contract "
    "or tort, even if advised of the possibility of such damages. " * 12,
)
print("chunks=====================>:", len(chunks))
print("===================chunks==================")
print(chunks)
print("===================chunks==================")


for c in chunks:
    print(c.token_count, "|", c.embed_text[:90].replace("\n", " "), "...")