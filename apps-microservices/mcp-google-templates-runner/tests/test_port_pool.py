import socket
import threading

import pytest
from app.port_pool import PortPool, PortPoolExhausted


# Tests of pure allocation logic use probe=False so we don't depend on which
# ports happen to be free on the host running the tests. The probe-path is
# covered by its own test below.


def test_allocate_in_order():
    pool = PortPool(15000, 15002)
    assert pool.allocate(probe=False) == 15000
    assert pool.allocate(probe=False) == 15001
    assert pool.allocate(probe=False) == 15002


def test_release_makes_available():
    pool = PortPool(15000, 15000)
    p = pool.allocate(probe=False)
    pool.release(p)
    assert pool.allocate(probe=False) == p


def test_exhausted_raises():
    pool = PortPool(15000, 15000)
    pool.allocate(probe=False)
    with pytest.raises(PortPoolExhausted):
        pool.allocate(probe=False)


def test_release_unknown_is_noop():
    pool = PortPool(15000, 15001)
    pool.release(9999)
    assert pool.allocate(probe=False) == 15000


def test_probe_skips_port_bound_outside_pool():
    """When a foreign process is listening on a port in the range, allocate
    with probe=True skips it and hands out the next free one."""
    # Bind a server on the first port of the pool so the probe detects it.
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))  # ephemeral
    server.listen(1)
    busy_port = server.getsockname()[1]

    # Keep accepting in the background so connect() actually succeeds.
    stop = threading.Event()

    def accept_loop():
        server.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = server.accept()
                conn.close()
            except socket.timeout:
                continue
            except OSError:
                return

    t = threading.Thread(target=accept_loop, daemon=True)
    t.start()

    try:
        # A pool that only contains the busy port should fail…
        pool_busy = PortPool(busy_port, busy_port)
        with pytest.raises(PortPoolExhausted):
            pool_busy.allocate()

        # …and a pool that also contains the next port should skip busy and
        # hand out busy+1.
        pool = PortPool(busy_port, busy_port + 1)
        got = pool.allocate()
        assert got == busy_port + 1
    finally:
        stop.set()
        server.close()
        t.join(timeout=1)
