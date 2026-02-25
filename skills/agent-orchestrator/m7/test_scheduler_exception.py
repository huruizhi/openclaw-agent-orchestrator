from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from m7.scheduler_exception import classify_scheduler_exception


def test_classify_timeout_as_transient():
    d = classify_scheduler_exception("dispatch", TimeoutError("x"))
    assert d.kind == "transient"
    assert d.error_code.startswith("SCHED_DISPATCH_")
