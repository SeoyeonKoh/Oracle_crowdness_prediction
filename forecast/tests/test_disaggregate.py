"""10분 분해 총량보존 테스트. (pytest 없이도 `python3 tests/test_disaggregate.py` 실행 가능)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.congestion.occupancy import (          # noqa: E402
    normalize_shape, disaggregate_to_10min,
)

TOL = 1e-9


def test_flat_when_no_shape():
    """형태가 없으면 6등분 평탄 분배, 평균 == 원래값."""
    out = disaggregate_to_10min(120.0, None)
    assert len(out) == 6
    assert all(abs(v - 120.0) < TOL for v in out)
    assert abs(sum(out) / 6 - 120.0) < TOL


def test_total_preserved_with_shape():
    """어떤 형태든 6개 10분값의 평균 == 원래 1시간값 (총량보존)."""
    for shape in ([1, 2, 3, 3, 2, 1], [0, 0, 0, 6, 0, 0], [5, 5, 5, 5, 5, 5]):
        out = disaggregate_to_10min(60.0, shape)
        assert abs(sum(out) / 6 - 60.0) < 1e-6, (shape, out)
        assert all(v >= 0 for v in out)


def test_shape_texture_applied():
    """형태가 반영돼 슬롯 간 값이 달라진다(피크 슬롯이 더 큼)."""
    out = disaggregate_to_10min(10.0, [1, 1, 1, 4, 1, 1])
    assert out[3] == max(out)
    assert out[3] > out[0]


def test_normalize_shape_mean_one():
    sh = normalize_shape([1, 2, 3, 4, 5, 6])
    assert abs(sum(sh) / 6 - 1.0) < TOL


def test_normalize_shape_rejects_bad():
    assert normalize_shape([1, -1, 1, 1, 1, 1]) is None   # 음수
    assert normalize_shape([0, 0, 0, 0, 0, 0]) is None    # 합 0
    assert normalize_shape([1, 1, 1]) is None             # 길이 오류
    assert normalize_shape(None) is None


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"통과: {len(fns)}개")


if __name__ == "__main__":
    _run_all()
