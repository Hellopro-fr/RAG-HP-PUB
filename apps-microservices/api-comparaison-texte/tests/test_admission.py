from app.core.admission import SyncAdmission


def test_disabled_always_admits():
    a = SyncAdmission(0)
    assert all(a.try_acquire() for _ in range(100))


def test_caps_at_max_and_releases():
    a = SyncAdmission(1)
    assert a.try_acquire() is True
    assert a.try_acquire() is False
    a.release()
    assert a.try_acquire() is True


def test_release_floors_at_zero():
    a = SyncAdmission(2)
    a.release()
    a.release()
    assert a.try_acquire() is True
    assert a.try_acquire() is True
    assert a.try_acquire() is False
