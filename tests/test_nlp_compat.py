"""The optional NLP stack must stay on a patched, mutually compatible line."""
from __future__ import annotations

import pytest


def test_setfit_supports_the_patched_transformers_import_layout() -> None:
    pytest.importorskip("transformers")
    pytest.importorskip("setfit")

    import transformers
    from packaging.version import Version
    from setfit.compat import default_logdir

    assert Version(transformers.__version__) >= Version("5.10.4")
    assert Version(transformers.__version__) < Version("6")
    assert callable(default_logdir)
