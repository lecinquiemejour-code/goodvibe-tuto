# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Interface de chat en ligne de commande pour GoodVibe (Feature 1).

Permet de dialoguer avec GoodVibe directement dans la console en streaming
avec persistance des messages et sortie propre sur la commande 'quitte'.
"""

import sys

import confirmation
from agent import repondre
from config import verifier_config
from db import charger_historique, sauvegarder_message
from fragments import REPONSE, avec_markdown


def demander_confirmation(historique: list) -> None:
    """Pose la question de confirmation si le modèle a proposé une suppression.

    C'est le programme qui demande, hors de la boucle du modèle, et c'est la réponse
    tapée par l'utilisateur qui décide : l'équivalent du bouton de la page web.

    Args:
        historique: La mémoire de travail du chat, vidée si tout a été effacé.
    """
    demande = confirmation.en_attente()
    if demande is None:
        return
    try:
        reponse = input(f"GoodVibe > {confirmation.question(demande)} (oui / non) > ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        reponse = "non"
    if reponse in ("oui", "o", "yes", "y"):
        print(f"[{confirmation.confirmer()}]\n")
        if demande.type == confirmation.TOUT:
            historique.clear()
    else:
        print(f"[{confirmation.refuser()}]\n")


def lancer_chat() -> None:
    """Boucle principale de discussion dans le terminal."""
    try:
        verifier_config()
    except ValueError as e:
        print(f"\n[Configuration incomplète]\n{e}\n")
        sys.exit(1)

    print("\n" + "=" * 55)
    print("  GoodVibe — Votre assistant personnel du matin")
    print("  Tapez votre message, '/coulisses' ou 'quitte' pour sortir.")
    print("=" * 55 + "\n")

    historique = charger_historique()
    if historique:
        print(f"[{len(historique)} message(s) précédent(s) rechargé(s) depuis la mémoire]\n")

    voir_reflexion = True

    while True:
        try:
            saisie = input("Vous > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAu revoir !")
            break

        if not saisie:
            continue

        if saisie.lower() in ("quitte", "exit", "quit"):
            print("Au revoir !")
            break

        if saisie.lower() in ("/coulisses", "/reflexion"):
            voir_reflexion = not voir_reflexion
            etat = "activées" if voir_reflexion else "désactivées"
            print(f"[🧠 Coulisses (résumé de réflexion & outils) {etat}]\n")
            continue

        reponse_complete = []
        premier_fragment = True

        try:
            flux = repondre(saisie, historique=historique, voir_reflexion=voir_reflexion)
            for fragment, texte_affiche in avec_markdown(flux):
                if premier_fragment:
                    print("GoodVibe > ", end="", flush=True)
                    premier_fragment = False
                # Tout s'affiche ; seul le texte de la réponse est retenu
                print(texte_affiche, end="", flush=True)
                if fragment.nature == REPONSE:
                    reponse_complete.append(fragment.texte)
            print()  # Saut de ligne final
        except Exception as e:
            print(f"\n[Erreur inattendue : {e}]")

        texte_reponse = "".join(reponse_complete).strip()
        historique.append({"role": "user", "content": saisie})
        historique.append({"role": "assistant", "content": texte_reponse})

        # Sauvegarde en base de données SQLite
        sauvegarder_message(role="user", contenu=saisie)
        sauvegarder_message(role="assistant", contenu=texte_reponse)

        # Si le modèle a proposé une suppression, c'est ici que l'utilisateur tranche
        demander_confirmation(historique)


if __name__ == "__main__":
    lancer_chat()
