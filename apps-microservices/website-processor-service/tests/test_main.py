import sys


def test_recursion_limit_raised_at_import():
    import website_processor_service.main  # noqa: F401

    assert sys.getrecursionlimit() >= 20000
