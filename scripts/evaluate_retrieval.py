from __future__ import annotations

import json
from pathlib import Path

from app.rag.query import normalize_query


def tokens(text: str) -> set[str]:
    return {token.strip(".,:;!?€").casefold() for token in text.split() if len(token) > 2}


def main() -> None:
    path = Path("tests/evals/german_russian_rag.jsonl")
    examples = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    reciprocal_ranks: list[float] = []
    recalls: list[float] = []
    for example in examples:
        query = normalize_query(example["query"])
        query_tokens = tokens(query.search_text)
        ranked = sorted(
            example["documents"],
            key=lambda item: len(query_tokens & tokens(item["text"])),
            reverse=True,
        )
        rank = next(
            (
                index
                for index, item in enumerate(ranked, start=1)
                if item["id"] == example["relevant_id"]
            ),
            0,
        )
        recalls.append(float(0 < rank <= 5))
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
    print(f"Examples: {len(examples)}")
    print(f"Recall@5: {sum(recalls) / len(recalls):.3f}")
    print(f"MRR: {sum(reciprocal_ranks) / len(reciprocal_ranks):.3f}")
    print("Source accuracy and unsupported-answer rate require generated-answer annotations.")


if __name__ == "__main__":
    main()
