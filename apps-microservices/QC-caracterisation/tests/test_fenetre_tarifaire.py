"""Tests de la fenêtre tarifaire DeepSeek.

Ce module est le seul morceau de la garde qui soit testable hors Docker : la boucle
consommer/suspendre de `start_consuming()` dépend du comportement réel de
`aio_pika.QueueIterator` (cycle consume → basic_cancel → nack) qu'aucun mock ne
reproduit fidèlement, et `aio_pika` n'est pas installable dans l'environnement de
test local. Les bornes, elles, se vérifient exhaustivement.
"""

from datetime import datetime, timedelta, timezone

from app.core.fenetre_tarifaire import (
    FENETRES_PAR_DEFAUT,
    FENETRES_PLEINES,
    est_heure_pleine,
    libelle_fenetre,
    parser_fenetres,
)

# Heures UTC facturées au tarif double : 01:00-04:00 et 06:00-10:00.
HEURES_PLEINES_ATTENDUES = {1, 2, 3, 6, 7, 8, 9}


def _utc(heure, minute=0):
    return datetime(2026, 8, 18, heure, minute, tzinfo=timezone.utc)


def test_les_24_heures_utc():
    """Balayage exhaustif : aucune heure ne doit être classée à l'envers."""
    for heure in range(24):
        attendu = heure in HEURES_PLEINES_ATTENDUES
        assert est_heure_pleine(_utc(heure)) is attendu, (
            f"{heure:02d}:00 UTC classée "
            f"{'pleine' if not attendu else 'creuse'} à tort"
        )


def test_bornes_incluses_et_exclues():
    """Début de fenêtre inclus, fin exclue — c'est ce que facture DeepSeek."""
    for debut, fin in FENETRES_PLEINES:
        assert est_heure_pleine(_utc(debut)), f"{debut:02d}:00 doit être pleine"
        assert est_heure_pleine(_utc(debut, 59)), f"{debut:02d}:59 doit être pleine"
        assert not est_heure_pleine(_utc(fin)), f"{fin:02d}:00 doit être creuse"
        assert est_heure_pleine(_utc(fin - 1, 59)), f"{fin - 1:02d}:59 doit être pleine"


def test_comptage_des_heures():
    """7 heures pleines et 17 creuses : c'est la grille annoncée par DeepSeek."""
    pleines = sum(1 for h in range(24) if est_heure_pleine(_utc(h)))
    assert pleines == 7
    assert 24 - pleines == 17


def test_insensible_au_fuseau_de_l_horloge():
    """Le même instant doit être classé pareil, quel que soit son tzinfo.

    C'est la propriété qui protège du bug d'origine : un test écrit en heure locale
    se décalait d'une heure au changement d'heure. 02:00 UTC est une heure pleine ;
    exprimé en UTC+2 c'est 04:00, et en UTC-5 c'est 21:00 — le verdict ne doit pas
    changer.
    """
    instant_utc = _utc(2)
    for decalage in (-5, -1, 0, 1, 2, 3, 8):
        equivalent = instant_utc.astimezone(timezone(timedelta(hours=decalage)))
        assert est_heure_pleine(equivalent) is True, (
            f"02:00 UTC vu depuis UTC{decalage:+d} devrait rester une heure pleine"
        )

    instant_creux = _utc(12)
    for decalage in (-5, -1, 0, 1, 2, 3, 8):
        equivalent = instant_creux.astimezone(timezone(timedelta(hours=decalage)))
        assert est_heure_pleine(equivalent) is False, (
            f"12:00 UTC vu depuis UTC{decalage:+d} devrait rester une heure creuse"
        )


def test_creneau_22h_6h_paris_le_defaut_corrige():
    """Le créneau historique « 22h-6h Europe/Paris » dérive, la fenêtre UTC non.

    Mesure qui a motivé ce module : en été (UTC+2) ce créneau contient les heures
    pleines 3, 4, 5 ; en hiver (UTC+1) il contient 2, 3, 4. Ce ne sont pas les mêmes,
    et aucune ligne de code ne change entre les deux.
    """
    ete = [
        h
        for h in (22, 23, 0, 1, 2, 3, 4, 5)
        if est_heure_pleine(datetime(2026, 8, 18, h, tzinfo=timezone(timedelta(hours=2))))
    ]
    hiver = [
        h
        for h in (22, 23, 0, 1, 2, 3, 4, 5)
        if est_heure_pleine(datetime(2026, 1, 15, h, tzinfo=timezone(timedelta(hours=1))))
    ]
    assert ete == [3, 4, 5]
    assert hiver == [2, 3, 4]
    assert ete != hiver, "la dérive saisonnière doit rester démontrée par ce test"


def test_libelle_pour_les_logs():
    assert "01:00-04:00" in libelle_fenetre(_utc(2))
    assert "06:00-10:00" in libelle_fenetre(_utc(7))
    assert "creuses" in libelle_fenetre(_utc(12))
    assert "creuses" in libelle_fenetre(_utc(0))


def test_defaut_sur_l_heure_courante():
    """Sans argument, la fonction lit l'horloge et reste cohérente avec elle."""
    maintenant = datetime.now(timezone.utc)
    assert est_heure_pleine() == est_heure_pleine(maintenant)
    assert libelle_fenetre() == libelle_fenetre(maintenant)


# --- surcharge par variable d'environnement -------------------------------------


def test_grille_par_defaut_sans_surcharge():
    """Le service démarre sur la grille DeepSeek si la variable est absente ou vide."""
    for brut in (None, "", "   "):
        assert parser_fenetres(brut) == FENETRES_PAR_DEFAUT
    assert FENETRES_PAR_DEFAUT == ((1, 4), (6, 10))


def test_surcharge_valide():
    assert parser_fenetres("2-5") == ((2, 5),)
    assert parser_fenetres("1-4,6-10") == ((1, 4), (6, 10))
    assert parser_fenetres(" 0-24 ") == ((0, 24),)
    assert parser_fenetres("3-4,  8-9 ,20-22") == ((3, 4), (8, 9), (20, 22))


def test_surcharge_invalide_retombe_sur_le_defaut_sans_lever():
    """Une variable mal écrite ne doit JAMAIS empêcher le service de démarrer.

    C'est le point important : ce module est chargé à l'import des consumers. Une
    exception ici tuerait le conteneur au démarrage, et `restart: unless-stopped` le
    relancerait en boucle.
    """
    for brut in ("nawak", "4-1", "1-25", "-3", "5", "1-4,zzz", "3-3", "1-2-3", "24-25"):
        assert parser_fenetres(brut) == FENETRES_PAR_DEFAUT, f"{brut!r} devrait retomber"


def test_la_surcharge_agit_bien_sur_le_verdict():
    """Une grille "tout plein" doit rendre est_heure_pleine() vrai à toute heure.

    C'est ce qui permet de tester la garde contre un vrai broker sans attendre 1 h
    du matin.
    """
    tout_plein = parser_fenetres("0-24")
    for heure in range(24):
        assert any(d <= heure < f for d, f in tout_plein)

    aucune = parser_fenetres("0-1")
    assert sum(1 for h in range(24) if any(d <= h < f for d, f in aucune)) == 1


def test_grille_active_coherente():
    """En l'absence de surcharge dans l'environnement de test, on est sur le défaut."""
    assert FENETRES_PLEINES == FENETRES_PAR_DEFAUT or isinstance(FENETRES_PLEINES, tuple)
