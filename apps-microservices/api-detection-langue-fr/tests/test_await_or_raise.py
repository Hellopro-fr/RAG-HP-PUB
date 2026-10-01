"""Bornes des awaits Playwright qui n'ont aucun timeout natif.

Surface gardée : `_await_or_raise` et `_BoundedBrowserSemaphore`
(`app/services/scraper.py`). Avant elles, `new_context`, `add_cookies`,
`new_page`, `route`, `content` et l'attente d'un permis de navigateur étaient
les seuls awaits du chemin que rien ne bornait — `set_default_timeout` ne régit
que les méthodes acceptant un `timeout`, et aucune de ces cinq n'en accepte.
"""
import asyncio

import pytest

from app.core.config import settings
from app.services.redirect_tracker import _VARIANT_POINTLESS_ERRORS
from app.services.scraper import _await_or_raise, _BoundedBrowserSemaphore


async def _hangs():
    await asyncio.Event().wait()  # ne se résout jamais


class TestAwaitOrRaise:
    @pytest.mark.asyncio
    async def test_returns_the_result_when_it_arrives_in_time(self):
        async def quick():
            return "<html/>"

        assert await _await_or_raise(quick(), 5, "test") == "<html/>"

    @pytest.mark.asyncio
    async def test_raises_when_the_call_never_answers(self):
        with pytest.raises(TimeoutError):
            await _await_or_raise(_hangs(), 0.05, "new_context http://x")

    @pytest.mark.asyncio
    async def test_message_carries_a_variant_pointless_token(self):
        """Le message DOIT porter un jeton de `_VARIANT_POINTLESS_ERRORS`.

        Sans lui, `redirect_tracker` classe l'échec comme réparable par une
        variante d'URL et réarme TROIS navigations supplémentaires — pour un
        blocage navigateur qu'aucun basculement http/https ou www ne répare.
        Le jeton est lu depuis la vraie constante, jamais recopié ici : une
        copie ne comparerait qu'elle-même.
        """
        with pytest.raises(TimeoutError) as exc:
            await _await_or_raise(_hangs(), 0.05, "new_page http://x")
        assert any(tok in str(exc.value) for tok in _VARIANT_POINTLESS_ERRORS)

    @pytest.mark.asyncio
    async def test_does_not_cancel_the_overrunning_call(self):
        """La propriété qui justifie la forme non annulante.

        Annuler un appel Playwright en pleine conversation protocolaire est ce
        qui a orphelinné le callback de `page.goto` et produit le flood
        « Future exception was never retrieved ». Une borne ne doit pas
        rouvrir ça : l'appel en dépassement continue, il n'est pas annulé.
        """
        finished = asyncio.Event()

        async def slow():
            await asyncio.sleep(0.3)
            finished.set()

        with pytest.raises(TimeoutError):
            await _await_or_raise(slow(), 0.05, "test")

        await asyncio.wait_for(finished.wait(), timeout=3)
        assert finished.is_set(), "l'appel a été annulé au lieu d'être abandonné"

    @pytest.mark.asyncio
    async def test_propagates_the_calls_own_exception_unmasked(self):
        async def boom():
            raise RuntimeError("driver mort")

        with pytest.raises(RuntimeError, match="driver mort"):
            await _await_or_raise(boom(), 5, "test")


class TestBoundedBrowserSemaphore:
    @pytest.mark.asyncio
    async def test_grants_a_free_permit_without_waiting(self):
        sem = _BoundedBrowserSemaphore(1)
        async with sem:
            pass

    @pytest.mark.asyncio
    async def test_raises_when_no_permit_frees_up(self, monkeypatch):
        monkeypatch.setattr(settings, "BROWSER_POOL_WAIT_S", 0.05, raising=False)
        sem = _BoundedBrowserSemaphore(1)
        async with sem:
            with pytest.raises(TimeoutError) as exc:
                async with sem:
                    pass
        assert any(tok in str(exc.value) for tok in _VARIANT_POINTLESS_ERRORS)

    @pytest.mark.asyncio
    async def test_a_permit_granted_after_we_gave_up_goes_back_to_the_pool(
        self, monkeypatch
    ):
        """Le garde-fou qui compte vraiment.

        Sans lui, chaque attente échouée rétrécirait le pool d'un permis pour
        la vie du process — exactement la panne silencieuse que ce chantier
        existe pour empêcher. Assertion volontairement boîte-noire (une
        nouvelle entrée réussit) plutôt que sur `_value` : les internes
        d'`asyncio.Semaphore` diffèrent entre 3.10 (l'image) et 3.12 (ici).
        """
        monkeypatch.setattr(settings, "BROWSER_POOL_WAIT_S", 0.05, raising=False)
        sem = _BoundedBrowserSemaphore(1)
        may_release = asyncio.Event()

        async def holder():
            async with sem:
                await may_release.wait()

        h = asyncio.ensure_future(holder())
        await asyncio.sleep(0.01)  # laisse holder prendre le permis

        with pytest.raises(TimeoutError):
            async with sem:
                pass

        may_release.set()
        await h
        await asyncio.sleep(0.05)  # laisse le done-callback rendre le permis

        async with sem:
            pass  # ne lève pas => le pool n'a pas rétréci

    @pytest.mark.asyncio
    async def test_a_permit_granted_after_the_caller_was_cancelled_goes_back_to_the_pool(
        self, monkeypatch
    ):
        """L'annulation pendant l'attente est l'autre sortie, et la plus fréquente.

        L'appelant est annulé par le `wait_for` de l'item (300 s, `routes.py`)
        ou par `_abandon_job` (`async_jobs.py`). `asyncio.wait` n'annule pas la
        tâche d'acquisition : elle obtient le permis plus tard, et sans
        propriétaire personne ne le rend — `BROWSER_SEMAPHORE_SIZE` annulations
        suffisent à vider le pool pour la vie du process.
        """
        monkeypatch.setattr(settings, "BROWSER_POOL_WAIT_S", 30, raising=False)
        sem = _BoundedBrowserSemaphore(1)
        may_release = asyncio.Event()

        async def holder():
            async with sem:
                await may_release.wait()

        async def entrant():
            async with sem:
                pass

        h = asyncio.ensure_future(holder())
        await asyncio.sleep(0.01)  # laisse holder prendre le permis
        e = asyncio.ensure_future(entrant())
        await asyncio.sleep(0.01)  # laisse entrant se bloquer dans l'attente du pool

        e.cancel()
        with pytest.raises(asyncio.CancelledError):
            await e

        may_release.set()
        await h
        await asyncio.sleep(0.05)  # laisse l'acquisition orpheline prendre puis rendre

        monkeypatch.setattr(settings, "BROWSER_POOL_WAIT_S", 0.05, raising=False)
        async with sem:
            pass  # ne lève pas => le pool n'a pas rétréci

    @pytest.mark.asyncio
    async def test_a_permit_granted_in_the_same_tick_as_the_cancellation_goes_back_to_the_pool(
        self, monkeypatch
    ):
        """Le permis est accordé, puis l'appelant annulé, avant qu'il reprenne.

        L'acquisition est déjà terminée quand l'annulation atteint
        `asyncio.wait` : c'est le cas où un callback attaché « si pas fini »
        ne suffirait pas.
        """
        monkeypatch.setattr(settings, "BROWSER_POOL_WAIT_S", 30, raising=False)
        sem = _BoundedBrowserSemaphore(1)

        async def entrant():
            async with sem:
                pass

        async with sem:
            e = asyncio.ensure_future(entrant())
            await asyncio.sleep(0.01)  # laisse entrant se bloquer dans l'attente du pool
        # `__aexit__` ne suspend pas : rien n'a tourné entre la libération
        # ci-dessus et l'annulation ci-dessous.
        e.cancel()
        with pytest.raises(asyncio.CancelledError):
            await e
        await asyncio.sleep(0.05)  # laisse le permis revenir au pool

        monkeypatch.setattr(settings, "BROWSER_POOL_WAIT_S", 0.05, raising=False)
        async with sem:
            pass  # ne lève pas => le pool n'a pas rétréci

    @pytest.mark.asyncio
    async def test_holds_no_permit_when_entry_failed(self, monkeypatch):
        monkeypatch.setattr(settings, "BROWSER_POOL_WAIT_S", 0.05, raising=False)
        sem = _BoundedBrowserSemaphore(2)
        async with sem:
            async with sem:
                with pytest.raises(TimeoutError):
                    async with sem:
                        pass
        # les deux permis sont rendus, la troisième entrée échouée n'en a pris aucun
        async with sem:
            async with sem:
                pass


_PROXY = "http://user:pass@proxy.test:8000"


class _Driver:
    """Faux `Playwright` : ne compte que les appels à `stop()`."""

    def __init__(self) -> None:
        self.stop_calls = 0

    async def stop(self) -> None:
        self.stop_calls += 1


def _install_late_driver(monkeypatch, gate: asyncio.Event, driver: _Driver) -> None:
    """`async_playwright().start()` ne livre `driver` qu'une fois `gate` levé.

    Posé aux DEUX endroits d'où le code le lit : l'import de module de
    `scrape_html`, et l'import local de `scrape_html_with_redirects`.
    """
    import playwright.async_api

    from app.services import scraper

    class _Manager:
        async def start(self):
            await gate.wait()
            return driver

    monkeypatch.setattr(scraper, "async_playwright", _Manager)
    monkeypatch.setattr(playwright.async_api, "async_playwright", _Manager)


async def _until(predicate, timeout: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate() and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.01)


def _scrapers():
    from app.services import scraper

    return [scraper.scrape_html, scraper.scrape_html_with_redirects]


class TestLateDriverIsStopped:
    """Un driver livré APRÈS qu'on a cessé de l'attendre doit être arrêté.

    PROD 2026-09-24 : 42 drivers Playwright (`MainThread`) pour 4 navigateurs,
    39 encore vivants sans aucun navigateur une fois l'épisode résorbé — chacun
    né d'un `playwright.start` abandonné puis livré en retard, que plus rien ne
    référençait et que seul un redémarrage du conteneur tuait.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scrape", _scrapers(), ids=lambda f: f.__name__)
    async def test_a_driver_delivered_after_the_timeout_is_stopped(
        self, scrape, monkeypatch
    ):
        monkeypatch.setattr(settings, "BROWSER_OP_TIMEOUT_S", 0.05, raising=False)
        gate, driver = asyncio.Event(), _Driver()
        _install_late_driver(monkeypatch, gate, driver)

        try:
            await scrape("http://site.test/page", proxy=_PROXY)
        except TimeoutError:
            pass  # scrape_html lève ; la variante redirects rend un dict d'échec
        assert driver.stop_calls == 0  # rien à arrêter tant qu'il n'est pas livré

        gate.set()
        await _until(lambda: driver.stop_calls > 0)
        assert driver.stop_calls == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scrape", _scrapers(), ids=lambda f: f.__name__)
    async def test_a_driver_delivered_after_the_caller_was_cancelled_is_stopped(
        self, scrape, monkeypatch
    ):
        """L'autre sortie sans résultat : le `wait_for` de l'item, `_abandon_job`.

        `asyncio.wait` n'annule pas la tâche de démarrage — la leçon de R2 : une
        ressource prise par une tâche détachée doit avoir un propriétaire sur
        CHAQUE sortie de l'appelant, annulation comprise.
        """
        monkeypatch.setattr(settings, "BROWSER_OP_TIMEOUT_S", 30, raising=False)
        gate, driver = asyncio.Event(), _Driver()
        _install_late_driver(monkeypatch, gate, driver)

        caller = asyncio.ensure_future(scrape("http://site.test/page", proxy=_PROXY))
        await asyncio.sleep(0.05)  # l'appelant attend le driver
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller

        gate.set()
        await _until(lambda: driver.stop_calls > 0)
        assert driver.stop_calls == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scrape", _scrapers(), ids=lambda f: f.__name__)
    async def test_a_driver_delivered_in_time_is_stopped_once_not_twice(
        self, scrape, monkeypatch
    ):
        """Garde : le driver livré à temps n'est arrêté que par le `finally` normal."""
        from app.services import scraper

        async def launch_fails(*_a, **_k):
            raise RuntimeError("launch KO")

        monkeypatch.setattr(scraper, "_launch_browser", launch_fails)
        gate, driver = asyncio.Event(), _Driver()
        gate.set()
        _install_late_driver(monkeypatch, gate, driver)

        try:
            await scrape("http://site.test/page", proxy=_PROXY)
        except RuntimeError:
            pass
        await asyncio.sleep(0.1)  # laisse à un éventuel second arrêt le temps de partir
        assert driver.stop_calls == 1
