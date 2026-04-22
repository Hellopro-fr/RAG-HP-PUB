import pytest
from app.port_pool import PortPool, PortPoolExhausted


def test_allocate_in_order():
    pool = PortPool(15000, 15002)
    assert pool.allocate() == 15000
    assert pool.allocate() == 15001
    assert pool.allocate() == 15002


def test_release_makes_available():
    pool = PortPool(15000, 15000)
    p = pool.allocate()
    pool.release(p)
    assert pool.allocate() == p


def test_exhausted_raises():
    pool = PortPool(15000, 15000)
    pool.allocate()
    with pytest.raises(PortPoolExhausted):
        pool.allocate()


def test_release_unknown_is_noop():
    pool = PortPool(15000, 15001)
    pool.release(9999)
    assert pool.allocate() == 15000
