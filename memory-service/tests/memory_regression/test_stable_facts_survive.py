"""Scénarios de régression mémoire.

But : vérifier que les **faits stables survivent** aux cycles de consolidation
(merge) et de decay. Ce sont les garde-fous des contraintes non négociables #3
et #4 : un fait déclaré permanent ne doit jamais disparaître, une contradiction
doit toujours laisser une trace, et l'audit bi-temporel doit rester exact.

Tous les tests sont ``xfail`` tant que la logique métier n'est pas implémentée
(bootstrap = squelette). Ils décrivent le comportement ATTENDU, pas l'actuel.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.xfail(reason="logique métier non implémentée (bootstrap)", strict=False)


def test_permanent_fact_never_decays():
    """Un fait ``permanent=True`` conserve son importance après N cycles de decay.

    TODO:
        - Écrire un fait permanent (ex: date de naissance).
        - Lancer plusieurs cycles ``consolidation.decay.apply_decay``.
        - Vérifier importance inchangée + skipped_permanent > 0.
    """
    raise NotImplementedError


def test_situational_fact_decays_but_not_deleted():
    """Un fait situationnel voit son importance baisser sans être supprimé."""
    raise NotImplementedError


def test_contradiction_is_logged_never_silent():
    """Toute contradiction résolue par le merger apparaît dans contradiction_log.

    TODO: injecter deux faits contradictoires, lancer resolve_contradictions,
    vérifier qu'une ligne de log existe (contrainte #4).
    """
    raise NotImplementedError


def test_bitemporal_audit_as_of():
    """L'audit ``as_of`` renvoie l'état de connaissance à une date passée.

    TODO: fermer une arête (valid_until), interroger avant/après la fermeture,
    vérifier des résultats différents selon ``as_of``.
    """
    raise NotImplementedError


def test_forget_invalidates_but_preserves_audit_trail():
    """Un ``FORGET`` ferme le fait (valid_until) sans effacer l'historique."""
    raise NotImplementedError
