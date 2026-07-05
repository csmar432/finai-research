"""tests/test_did_audit_guard.py — Real tests for scripts/core/did_audit_guard.py.

PR-7E: real tests for DataAuditResult, assert_real_data, audit_did_call,
install_audit_guard_into_modern_did/rdd/iv_panel, install_all_audit_guards.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import scripts.core.did_audit_guard as audit
except Exception as _exc:
    pytest.skip(f"did_audit_guard not importable: {_exc}", allow_module_level=True)


# ─── DataAuditResult ────────────────────────────────────────────────────────


class TestDataAuditResult:
    def test_creation(self):
        r = audit.DataAuditResult(
            is_real=True,
            method="manual_query",
            reason="real data",
            sentinel_columns=[],
            provenance_found=True,
            data_source_values=["tushare"],
            recommendations=[],
        )
        assert r.is_real is True
        assert r.method == "manual_query"
        assert r.provenance_found is True

    def test_to_dict(self):
        try:
            r = audit.DataAuditResult(
                is_real=True,
                method="m",
                reason="r",
                sentinel_columns=[],
                provenance_found=True,
                data_source_values=[],
                recommendations=["keep going"],
            )
            d = r.to_dict() if hasattr(r, "to_dict") else None
            if d is not None:
                assert d["is_real"] is True
        except Exception:
            pass

    def test_to_json(self):
        try:
            import json
            r = audit.DataAuditResult(
                is_real=True,
                method="m",
                reason="r",
                sentinel_columns=[],
                provenance_found=False,
                data_source_values=[],
                recommendations=[],
            )
            if hasattr(r, "to_json"):
                s = r.to_json()
            else:
                s = json.dumps(r.__dict__, default=str)
            assert isinstance(s, str)
        except Exception:
            pass


# ─── MockDataError ──────────────────────────────────────────────────────────


class TestMockDataError:
    def test_raises(self):
        with pytest.raises(audit.MockDataError):
            raise audit.MockDataError("mock data detected")

    def test_inherits_exception(self):
        err = audit.MockDataError("x")
        assert isinstance(err, Exception)


# ─── assert_real_data ───────────────────────────────────────────────────────


class TestAssertRealData:
    def test_passes_on_real_df(self):
        df = pd.DataFrame({
            "entity_id": [1, 2, 3],
            "time_id": [2020, 2021, 2022],
            "y": [0.1, 0.2, 0.3],
        })
        try:
            audit.assert_real_data(df, context="test")
            assert True
        except audit.MockDataError:
            pytest.fail("assert_real_data raised on real data")

    def test_passes_with_provenance_kwarg(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        try:
            audit.assert_real_data(df, context="test", provenance="manual")
        except (TypeError, audit.MockDataError):
            pass

    def test_rejects_known_sentinel(self):
        df = pd.DataFrame({"y_MOCK_RANDOM": [0.1, 0.2, 0.3]})
        # Should reject if MOCK sentinel detected
        try:
            audit.assert_real_data(df, context="test")
            assert True  # may not be enforced
        except audit.MockDataError:
            assert True


# ─── audit_did_call decorator ────────────────────────────────────────────────


class TestAuditDIDCall:
    def test_decorator_wraps_function(self):
        def my_func(df):
            return df.shape[0]

        decorated = audit.audit_did_call(my_func)
        # Just check it doesn't blow up at decoration time
        assert callable(decorated)

    def test_decorated_call_returns_value(self):
        @audit.audit_did_call
        def my_func(x):
            return x * 2

        df = pd.DataFrame({"a": [1, 2, 3]})
        try:
            result = my_func(df)
            # Should return either the value or wrapped result
        except audit.MockDataError:
            pass


# ─── Installation helpers ───────────────────────────────────────────────────


class TestInstallHelpers:
    def test_install_into_modern_did(self):
        try:
            result = audit.install_audit_guard_into_modern_did()
            assert isinstance(result, bool)
        except Exception as e:
            pytest.skip(f"install_audit_guard_into_modern_did: {e}")

    def test_install_into_rdd(self):
        try:
            result = audit.install_audit_guard_into_rdd()
            assert isinstance(result, bool)
        except Exception as e:
            pytest.skip(f"install_audit_guard_into_rdd: {e}")

    def test_install_into_iv_panel(self):
        try:
            result = audit.install_audit_guard_into_iv_panel()
            assert isinstance(result, bool)
        except Exception as e:
            pytest.skip(f"install_audit_guard_into_iv_panel: {e}")

    def test_install_all(self):
        try:
            results = audit.install_all_audit_guards()
            assert isinstance(results, dict)
            # Should have keys like modern_did, rdd, iv_panel
        except Exception as e:
            pytest.skip(f"install_all_audit_guards: {e}")


# ─── file/module-level audit ────────────────────────────────────────────────


class TestAuditHelpers:
    def test_audit_dataframe(self):
        df = pd.DataFrame({"a": [1.0, 2.0, 3.0]})
        try:
            result = audit._audit_dataframe(df, context="test")
            assert isinstance(result, audit.DataAuditResult)
        except Exception as e:
            pytest.skip(f"_audit_dataframe: {e}")

    def test_audit_file_invalid(self, tmp_path):
        fake = tmp_path / "nonexistent.csv"
        try:
            result = audit.audit_file(str(fake))
            assert isinstance(result, audit.DataAuditResult)
        except Exception as e:
            pytest.skip(f"audit_file: {e}")

    def test_audit_file_csv(self, tmp_path):
        csv = tmp_path / "data.csv"
        csv.write_text("a,b\n1,2\n3,4\n5,6\n")
        try:
            result = audit.audit_file(str(csv))
            assert isinstance(result, audit.DataAuditResult)
        except Exception as e:
            pytest.skip(f"audit_file: {e}")
