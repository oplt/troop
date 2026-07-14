from backend.tools.check_external_call_policy import find_policy_violations


def test_runtime_http_clients_use_the_shared_pool():
    assert find_policy_violations() == []
