from hope_core.schemas.agency_profile import Program
from hope_matching.alignment import (
    JudgeSample,
    aggregate,
    assess_alignment,
    hybrid_search,
    profile_passages,
    rrf,
)
from hope_matching.config import MatchingConfig
from hope_matching.contracts import RUBRIC
from hope_matching.testing import gateway, opportunity, profile, scores_judge


def test_rrf_fuses_rankings() -> None:
    fused = rrf([["a", "b", "c"], ["c", "a"]])
    assert [doc for doc, _ in fused] == ["a", "c", "b"]
    assert fused[0][1] == 1 / 61 + 1 / 62


def test_hybrid_search_prefers_lexical_match() -> None:
    p = profile(
        programs=[
            Program(program_id="p-food", name="Food Pantry", description="Groceries for seniors."),
            Program(program_id="p-stem", name="Robotics Lab", description="Robotics and coding."),
        ]
    )
    hits = hybrid_search(gateway(), profile_passages(p), "robotics coding youth", top_k=2)
    assert hits[0].evidence_id == "program:p-stem"


def test_assessment_takes_median_and_cites_evidence() -> None:
    judge = scores_judge({d: [70.0, 80.0, 75.0] for d in RUBRIC})
    result = assess_alignment(gateway(judge), profile(), opportunity())
    assert result.score == 75.0
    assert all(d.samples == [70.0, 80.0, 75.0] for d in result.dimension_scores)
    assert all(d.evidence_ids and not d.low_confidence for d in result.dimension_scores)
    assert set(result.retrieved_evidence_ids) >= {
        d.evidence_ids[0] for d in result.dimension_scores
    }
    assert not result.low_confidence


def test_high_variance_is_low_confidence() -> None:
    judge = scores_judge({"geography": [10.0, 90.0, 50.0]})
    result = assess_alignment(gateway(judge), profile(), opportunity())
    geo = next(d for d in result.dimension_scores if d.dimension == "geography")
    assert geo.score == 50.0 and geo.low_confidence
    assert result.low_confidence


def _sample(score: float, ids: list[str]) -> JudgeSample:
    return JudgeSample.model_validate(
        {
            "dimensions": [
                {"dimension": d, "score": score, "evidence_ids": ids, "rationale": "r"}
                for d in RUBRIC
            ]
        }
    )


def test_uncited_or_unknown_evidence_is_rejected() -> None:
    samples = [_sample(90, []), _sample(90, ["made-up"]), _sample(40, ["mission"])]
    dims = aggregate(samples, {"mission"}, 15)
    assert all(d.score == 40 and d.rejected_samples == 2 and d.low_confidence for d in dims)
    none = aggregate([_sample(90, [])], {"mission"}, 15)
    assert all(d.score == 0 and d.low_confidence for d in none)


def test_matched_programs_and_gaps() -> None:
    judge = scores_judge({"capacity": [20.0, 20.0, 20.0]})
    cfg = MatchingConfig(retrieval_top_k=20)
    result = assess_alignment(gateway(judge), profile(), opportunity(), cfg)
    assert "capacity: 20" in result.gaps
    cited = {e for d in result.dimension_scores for e in d.evidence_ids}
    assert result.matched_programs == (["prog-stem"] if "program:prog-stem" in cited else [])


def test_judge_sees_untrusted_wrapped_content() -> None:
    seen: list[str] = []

    def judge(sample: int, ids: list[str]) -> dict[str, object]:
        seen.append(str(sample))
        return scores_judge()(sample, ids)

    assess_alignment(gateway(judge), profile(), opportunity())
    assert seen == ["1", "2", "3"]
