from eew.evaluation import evaluate_case, summarize


def test_evaluation_separates_detection_duplicates_and_false_candidates() -> None:
    case = {
        "id": "event",
        "kind": "historical_earthquake",
        "origin_time": "2026-01-01T00:00:00Z",
    }
    replay = {
        "candidates": [
            {"detected_at": "2025-12-31T23:59:50Z"},
            {"detected_at": "2026-01-01T00:00:20Z"},
            {"detected_at": "2026-01-01T00:00:40Z"},
        ]
    }
    result = evaluate_case(case, replay)
    assert result["detected"] is True
    assert result["detection_latency_seconds"] == 20
    assert result["false_candidate_count"] == 1
    assert result["duplicate_candidate_count"] == 1


def test_summary_penalizes_noise_more_than_latency() -> None:
    clean = [
        {
            "kind": "historical_earthquake",
            "detected": True,
            "detection_latency_seconds": 40.0,
            "false_candidate_count": 0,
            "duplicate_candidate_count": 0,
        },
        {
            "kind": "ambient_noise",
            "detected": False,
            "detection_latency_seconds": None,
            "false_candidate_count": 0,
            "duplicate_candidate_count": 0,
        },
    ]
    noisy = [dict(item) for item in clean]
    noisy[1]["false_candidate_count"] = 1
    assert summarize(clean)["engineering_score"] < summarize(noisy)["engineering_score"]
