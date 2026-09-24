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
