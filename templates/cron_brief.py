# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Point d'entrée autonome pour la génération automatique du brief matinal (Feature 6).

Ce script est destiné à être exécuté par un cron système (ex: à 7 h du matin sur le VPS à la Fiche 12)
ou manuellement en ligne de commande.

Usage :
    python cron_brief.py
    python cron_brief.py --forcer
"""

import argparse
import sys

from brief import generer_brief
from config import verifier_config


def main() -> None:
    """Exécute la génération du brief en ligne de commande."""
    try:
        verifier_config()
    except ValueError as e:
        print(f"\n[Erreur de configuration] {e}\n", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="Génération du brief matinal personnalisé GoodVibe."
    )
    parser.add_argument(
        "--forcer",
        action="store_true",
        help="Force la génération du brief même s'il a déjà été produit aujourd'hui.",
    )
    args = parser.parse_args()

    # Consommation en silence : seul le journal garde la trace, encadrée par « cron:brief »
    resultat = generer_brief(forcer=args.forcer, declencheur="cron")
    if "déjà produit" in resultat.lower():
        print(resultat)


if __name__ == "__main__":
    main()
