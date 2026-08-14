"""Evaluation case scoring helpers."""

from backend.modules.ai.evaluations.assertions import evaluate_assertions


def score_evaluation_case(
    output_text: str | None, output_json: dict | None, case
) -> tuple[float, bool, str]:
    assertions = getattr(case, "expected_assertions_json", None)
    if assertions:
        return evaluate_assertions(
            output_text=output_text,
            output_json=output_json,
            assertions=assertions,
        )
    if case.expected_output_json is not None:
        passed = output_json == case.expected_output_json
        return (1.0 if passed else 0.0, passed, "JSON exact match")
    expected_text = (case.expected_output_text or "").strip()
    actual_text = (output_text or "").strip()
    if expected_text:
        passed = expected_text.lower() == actual_text.lower()
        if passed:
            return 1.0, True, "Exact text match"
        partial = 1.0 if expected_text.lower() in actual_text.lower() else 0.0
        return partial, partial >= 1.0, "Substring text comparison"
    return 0.0, False, "No expected output defined"
