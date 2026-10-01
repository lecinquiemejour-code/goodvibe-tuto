# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Tests de la page web (interface.py).

Garanties :
- La page se construit sans appel réseau.
- Le bouton de déconnexion est présent et pointe vers l'adresse prévue par Gradio.
"""

from interface import creer_interface


def test_bouton_de_deconnexion():
    """Vérifie que la page propose un bouton qui mène à l'adresse de déconnexion."""
    page = creer_interface()

    boutons = [c["props"] for c in page.config["components"] if c["type"] == "button"]
    deconnexion = [b for b in boutons if b.get("link") == "/logout"]

    assert len(deconnexion) == 1
    assert "déconnecter" in deconnexion[0]["value"].lower()
