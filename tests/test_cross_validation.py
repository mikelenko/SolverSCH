"""
test_cross_validation.py — Unit test for LTspice Comparator logic.

Tests the comparator pipeline with mock data (no LTspice binary required).
Validates that PASS / WARN / FAIL thresholds work correctly.
"""
import pytest
from solver_sch.results import DcAnalysisResult, AcAnalysisResult, NodeAcResult, TransientTimepoint
from solver_sch.utils.ltspice_comparator import LTspiceComparator, ComparisonResult


class TestDcComparison:
    """DC cross-validation between SolverSCH and mocked LTspice results."""

    def test_dc_pass_identical(self):
        """Identical values should PASS with 0% error."""
        solver_dc = DcAnalysisResult(
            node_voltages={"in": 5.0, "out": 3.3},
            source_currents={"V1": -0.001},
        )
        ltspice_dc = {"in": 5.0, "out": 3.3}

        result = LTspiceComparator.compare_dc(solver_dc, ltspice_dc, tolerance_pct=0.1)

        assert result.passed is True
        assert result.max_error_pct == 0.0
        assert all(n.status == "PASS" for n in result.nodes)

    def test_dc_pass_within_tolerance(self):
        """Small error within tolerance should PASS."""
        solver_dc = DcAnalysisResult(
            node_voltages={"out": 3.300},
            source_currents={},
        )
        ltspice_dc = {"out": 3.301}  # 0.03% error

        result = LTspiceComparator.compare_dc(solver_dc, ltspice_dc, tolerance_pct=0.1)

        assert result.passed is True
        assert result.max_error_pct < 0.1

    def test_dc_fail_outside_tolerance(self):
        """Large error should FAIL."""
        solver_dc = DcAnalysisResult(
            node_voltages={"out": 3.0},
            source_currents={},
        )
        ltspice_dc = {"out": 3.5}  # ~14% error

        result = LTspiceComparator.compare_dc(solver_dc, ltspice_dc, tolerance_pct=0.1)

        assert result.passed is False
        assert any(n.status == "FAIL" for n in result.nodes)

    def test_dc_warn_threshold(self):
        """Error between tolerance/2 and tolerance should WARN."""
        solver_dc = DcAnalysisResult(
            node_voltages={"out": 3.300},
            source_currents={},
        )
        # 0.07% error → between 0.05% (tol/2) and 0.1% (tol)
        ltspice_dc = {"out": 3.30231}

        result = LTspiceComparator.compare_dc(solver_dc, ltspice_dc, tolerance_pct=0.1)

        assert result.passed is True  # WARN still counts as passed
        assert any(n.status == "WARN" for n in result.nodes)

    def test_dc_missing_node(self):
        """Node missing in LTspice should FAIL."""
        solver_dc = DcAnalysisResult(
            node_voltages={"out": 3.3, "missing_node": 1.0},
            source_currents={},
        )
        ltspice_dc = {"out": 3.3}  # missing_node not in LTspice

        result = LTspiceComparator.compare_dc(solver_dc, ltspice_dc, tolerance_pct=0.1)

        assert result.passed is False
        missing = [n for n in result.nodes if n.node == "missing_node"]
        assert len(missing) == 1
        assert missing[0].status == "FAIL"

    def test_dc_case_insensitive_match(self):
        """LTspice sometimes uses different casing — should still match."""
        solver_dc = DcAnalysisResult(
            node_voltages={"out": 3.3},
            source_currents={},
        )
        ltspice_dc = {"OUT": 3.3}

        result = LTspiceComparator.compare_dc(solver_dc, ltspice_dc, tolerance_pct=0.1)

        assert result.passed is True


class TestAcComparison:
    """AC cross-validation tests."""

    def test_ac_pass_identical(self):
        """Identical AC magnitudes should PASS."""
        solver_ac = AcAnalysisResult(
            frequencies=[100.0, 1000.0, 10000.0],
            nodes={
                "out": NodeAcResult(
                    node="out",
                    magnitude=[1.0, 0.707, 0.1],
                    magnitude_db=[-0.0, -3.01, -20.0],
                    phase_deg=[0.0, -45.0, -84.3],
                )
            },
            f_start=100.0,
            f_stop=10000.0,
        )
        ltspice_freqs = [100.0, 1000.0, 10000.0]
        ltspice_ac = {"out": [1.0 + 0j, 0.707 + 0j, 0.1 + 0j]}

        result = LTspiceComparator.compare_ac(solver_ac, ltspice_freqs, ltspice_ac, tolerance_pct=1.0)

        assert result.passed is True
        assert result.max_error_pct < 1.0

    def test_ac_fail_large_deviation(self):
        """Large magnitude mismatch should FAIL."""
        solver_ac = AcAnalysisResult(
            frequencies=[100.0, 1000.0, 10000.0],
            nodes={
                "out": NodeAcResult(
                    node="out",
                    magnitude=[1.0, 0.707, 0.1],
                    magnitude_db=[-0.0, -3.01, -20.0],
                    phase_deg=[0.0, -45.0, -84.3],
                )
            },
            f_start=100.0,
            f_stop=10000.0,
        )
        ltspice_freqs = [100.0, 1000.0, 10000.0]
        # Completely wrong magnitudes
        ltspice_ac = {"out": [0.5 + 0j, 0.3 + 0j, 0.05 + 0j]}

        result = LTspiceComparator.compare_ac(solver_ac, ltspice_freqs, ltspice_ac, tolerance_pct=1.0)

        assert result.passed is False


class TestTransientComparison:
    """Transient cross-validation tests."""

    def test_transient_pass_identical(self):
        """Identical transient waveforms should PASS."""
        solver_tran = [
            TransientTimepoint(time=0.0, node_voltages={"out": 0.0}),
            TransientTimepoint(time=0.001, node_voltages={"out": 2.5}),
            TransientTimepoint(time=0.002, node_voltages={"out": 5.0}),
        ]
        ltspice_times = [0.0, 0.001, 0.002]
        ltspice_tran = {"out": [0.0, 2.5, 5.0]}

        result = LTspiceComparator.compare_transient(solver_tran, ltspice_times, ltspice_tran, tolerance_pct=2.0)

        assert result.passed is True


class TestComparisonResultSerialization:
    """Test JSON serialization of ComparisonResult."""

    def test_to_json(self):
        """ComparisonResult should serialize to valid JSON."""
        solver_dc = DcAnalysisResult(
            node_voltages={"out": 3.3},
            source_currents={},
        )
        ltspice_dc = {"out": 3.3}

        result = LTspiceComparator.compare_dc(solver_dc, ltspice_dc, tolerance_pct=0.1)
        json_str = result.to_json()

        assert '"analysis": "dc"' in json_str
        assert '"passed": true' in json_str

    def test_summary(self):
        """summary() should return a human-readable string."""
        solver_dc = DcAnalysisResult(
            node_voltages={"out": 3.3},
            source_currents={},
        )
        ltspice_dc = {"out": 3.3}

        result = LTspiceComparator.compare_dc(solver_dc, ltspice_dc, tolerance_pct=0.1)
        summary = result.summary()

        assert "PASSED" in summary
        assert "DC" in summary
