import json
import time
from pathlib import Path

import requests


API_URL = "http://127.0.0.1:8000/chat"
REPOSITORY_ID = 1

QUESTIONS_FILE = (
    Path(__file__).parent / "retrieval_questions.json"
)


def normalize_path(path: str) -> str:
    path = path.replace("\\", "/").lstrip("./")

    if path.startswith("backend/"):
        return path

    return path


def is_expected(
    file_path: str,
    expected_files: list[str],
) -> bool:
    normalized = normalize_path(file_path)

    return any(
        normalized == normalize_path(expected)
        or normalized.endswith(normalize_path(expected))
        for expected in expected_files
    )


def reciprocal_rank(
    returned_files: list[str],
    expected_files: list[str],
) -> float:
    for index, file_path in enumerate(
        returned_files,
        start=1,
    ):
        if is_expected(
            file_path,
            expected_files,
        ):
            return 1.0 / index

    return 0.0


def evaluate_question(
    question_data: dict,
) -> dict:
    question = question_data["question"]
    expected_files = question_data["expected_files"]

    started = time.perf_counter()

    response = requests.post(
        API_URL,
        json={
            "repository_id": REPOSITORY_ID,
            "message": question,
        },
        timeout=120,
    )

    latency = time.perf_counter() - started

    response.raise_for_status()

    data = response.json()

    sources = data.get("sources", [])

    returned_files = [
        source.get("file_path", "")
        for source in sources
        if source.get("file_path")
    ]

    hit_at_1 = any(
        is_expected(
            file_path,
            expected_files,
        )
        for file_path in returned_files[:1]
    )

    hit_at_3 = any(
        is_expected(
            file_path,
            expected_files,
        )
        for file_path in returned_files[:3]
    )

    hit_at_5 = any(
        is_expected(
            file_path,
            expected_files,
        )
        for file_path in returned_files[:5]
    )

    return {
        "question": question,
        "expected_files": expected_files,
        "returned_files": returned_files,
        "hit_at_1": int(hit_at_1),
        "hit_at_3": int(hit_at_3),
        "hit_at_5": int(hit_at_5),
        "mrr": reciprocal_rank(
            returned_files,
            expected_files,
        ),
        "latency_seconds": round(
            latency,
            3,
        ),
    }


def main():
    with open(
        QUESTIONS_FILE,
        "r",
        encoding="utf-8",
    ) as file:
        questions = json.load(file)

    results = []

    print()
    print("=" * 70)
    print("RETRIEVAL EVALUATION")
    print("=" * 70)

    for index, question in enumerate(
        questions,
        start=1,
    ):
        print()
        print(
            f"[{index}/{len(questions)}] "
            f"{question['question']}"
        )

        try:
            result = evaluate_question(question)

            results.append(result)

            print(
                f"  Hit@1: {result['hit_at_1']} | "
                f"Hit@3: {result['hit_at_3']} | "
                f"Hit@5: {result['hit_at_5']} | "
                f"MRR: {result['mrr']:.3f}"
            )

            top_result = (
                result["returned_files"][0]
                if result["returned_files"]
                else "NONE"
            )

            print(
                f"  Top result: {top_result}"
            )

            print(
                f"  Latency: "
                f"{result['latency_seconds']}s"
            )

        except Exception as exc:
            print(f"  ERROR: {exc}")

    if not results:
        print()
        print("No evaluation results were produced.")
        return

    total = len(results)

    hit_at_1 = sum(
        result["hit_at_1"]
        for result in results
    ) / total

    hit_at_3 = sum(
        result["hit_at_3"]
        for result in results
    ) / total

    hit_at_5 = sum(
        result["hit_at_5"]
        for result in results
    ) / total

    mrr = sum(
        result["mrr"]
        for result in results
    ) / total

    avg_latency = sum(
        result["latency_seconds"]
        for result in results
    ) / total

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    print(f"Questions:     {total}")
    print(f"Hit@1:         {hit_at_1:.3f}")
    print(f"Hit@3:         {hit_at_3:.3f}")
    print(f"Hit@5:         {hit_at_5:.3f}")
    print(f"MRR:           {mrr:.3f}")
    print(f"Avg latency:   {avg_latency:.3f}s")

    print("=" * 70)


if __name__ == "__main__":
    main()