from utils.status_semantics import compose_status


def test_status_mapping_done():
    s = compose_status("completed", "finished")
    assert s.status_view == "done"


def test_status_mapping_waiting():
    s = compose_status("waiting_human", "running")
    assert s.status_view == "waiting"
