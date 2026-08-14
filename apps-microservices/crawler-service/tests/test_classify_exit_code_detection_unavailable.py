"""Exit code 10 (detection unavailable) must classify as a detection_unavailable failure."""

from app.core.crawler_manager import CrawlerManager


def test_exit_10_classifies_as_detection_unavailable():
    message, failure_cause = CrawlerManager._classify_exit_code(10)
    assert failure_cause == "detection_unavailable"
    assert message is not None and len(message) > 0


def test_exit_10_is_not_unknown():
    message, failure_cause = CrawlerManager._classify_exit_code(10)
    assert failure_cause != "unknown"
    assert "inattendue" not in message  # not the catch-all "Erreur inattendue" branch


def test_exit_10_is_a_failure_not_success():
    """Épingle l'allowlist `is_success` DANS LA SOURCE, pour que l'élargir casse ce test.

    La version précédente affirmait `assert 10 not in (0, 2)` : une tautologie sur des
    littéraux, qui passait inchangée quoi que fasse le module. Or l'édition qu'elle est
    censée garder — ajouter 10 à `is_success` — renverrait au webhook de SUCCÈS un crawl
    qui n'a rien produit, c'est-à-dire exactement le défaut que l'exit 10 existe pour
    fermer. C'était la seule direction non gardée de cette suite.

    `is_success` est une locale de `_monitor_process` : elle ne peut pas s'importer. Le
    contrôle honnête porte donc sur le texte de la source, même technique que
    `statNameParity.test.ts` côté TypeScript pour une constante non exécutable.
    """
    import inspect
    import re

    from app.core import crawler_manager

    source = inspect.getsource(crawler_manager)
    matches = re.findall(r"is_success\s*=\s*\(\s*exit_code in \(([^)]*)\)\s*\)", source)
    assert len(matches) == 1, (
        f"attendu exactement une allowlist is_success, trouvé {len(matches)} — "
        "si elle a été déplacée ou dupliquée, re-dériver ce test au lieu de l'assouplir"
    )
    allowed = {int(tok) for tok in matches[0].replace(" ", "").split(",") if tok}
    assert 10 not in allowed, (
        f"exit 10 a été ajouté à l'allowlist is_success {allowed} : cela INVERSE le "
        "correctif — un crawl sans verdict de homepage repartirait en webhook de succès"
    )
    assert allowed == {0, 2}, (
        f"l'allowlist is_success vaut désormais {allowed} et non (0, 2) : re-dériver "
        "si l'exit 10 est toujours classé en échec avant de toucher à ce test"
    )


def test_neighbour_branches_are_untouched():
    # The new branch sits just above 137/-9: neither may be shadowed.
    assert CrawlerManager._classify_exit_code(137)[1] == "killed_oom_system"
    assert CrawlerManager._classify_exit_code(-9)[1] == "killed_oom_system"
    assert CrawlerManager._classify_exit_code(9)[1] == "domain_dead"


def test_success_codes_still_return_none():
    assert CrawlerManager._classify_exit_code(0) == (None, None)
    assert CrawlerManager._classify_exit_code(2) == (None, None)
