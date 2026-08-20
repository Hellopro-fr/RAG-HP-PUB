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
