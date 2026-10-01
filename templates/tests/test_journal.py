# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Tests unitaires du journal d'observabilité de GoodVibe (journal.py).

Vérifie l'enregistrement des événements, l'isolation technique et la consultation.
"""

from journal import (
    consigner_activite,
    get_dernieres_activites,
    lire_journal_execution,
)


def test_consigner_et_lire_activite():
    """Vérifie l'insertion dans la table journal et la lecture ordonnée."""
    consigner_activite(
        etape="chat",
        detail="Échange conversationnel test",
        tokens_entree=150,
        tokens_sortie=45,
        tokens_reflexion=20,
        latence_ms=310,
        duree_ms=1250,
    )

    activites = get_dernieres_activites(limite=5)
    assert len(activites) >= 1
    derniere = activites[0]
    assert derniere["etape"] == "chat"
    assert derniere["detail"] == "Échange conversationnel test"
    assert derniere["tokens_entree"] == 150
    assert derniere["tokens_sortie"] == 45
    assert derniere["tokens_reflexion"] == 20
    assert derniere["latence_ms"] == 310
    assert derniere["duree_ms"] == 1250


def test_lire_journal_par_execution_id():
    """Vérifie le filtrage des étapes du journal par identifiant d'exécution."""
    exec_id = "exec_test_999"
    consigner_activite(etape="brief:etape1", detail="Début brief", execution_id=exec_id)
    consigner_activite(etape="brief:etape2", detail="Fin brief", execution_id=exec_id)

    etapes = lire_journal_execution(execution_id=exec_id)
    assert len(etapes) == 2
    assert etapes[0]["etape"] == "brief:etape1"
    assert etapes[1]["etape"] == "brief:etape2"
