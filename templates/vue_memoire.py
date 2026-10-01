# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Vue de la mémoire locale de GoodVibe pour l'interface Gradio.

Affiche en lecture seule les 4 tables qui contiennent ce que l'agent sait de l'utilisateur :
- profil : informations personnelles retenues par l'agent
- notes : notes personnelles enregistrées
- conversations : historique des échanges persistés
- pense_betes : messages reçus par le webhook

La table traites (verrous anti-doublon) n'est pas affichée : elle ne contient
aucune information sur l'utilisateur. Elle reste utilisée par le brief et l'image.

Toutes les dates sont affichées à l'heure du navigateur client (détection JS).
Fournit également un bouton 'Oublie-moi' avec confirmation explicite : l'effacement
complet est fait par oubli.py, le même que celui confirmé depuis le chat.
"""

from datetime import datetime, timezone
from typing import Any, List, Optional
from zoneinfo import ZoneInfo

import gradio as gr

from db import LIBELLES_STATUT_PENSE_BETE, get_connection
from oubli import AVERTISSEMENT_EFFACEMENT, effacer_utilisateur


def obtenir_fuseau(nom_fuseau: Optional[str] = None) -> ZoneInfo:
    """Résout le fuseau horaire du navigateur client, ou à défaut celui du système local."""
    if nom_fuseau:
        try:
            return ZoneInfo(nom_fuseau.strip())
        except Exception:
            pass
    try:
        return datetime.now().astimezone().tzinfo or ZoneInfo("Europe/Paris")
    except Exception:
        return ZoneInfo("Europe/Paris")


def convertir_date_client(date_iso: str, fuseau: Optional[str] = None) -> str:
    """Convertit un timestamp ISO en date et heure du navigateur client (JJ/MM/AAAA HH:MM:SS)."""
    if not date_iso:
        return "-"
    try:
        dt = datetime.fromisoformat(date_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        tz = obtenir_fuseau(fuseau)
        dt_local = dt.astimezone(tz)
        return dt_local.strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return date_iso


def charger_profil_tableau(fuseau: Optional[str] = None) -> List[List[Any]]:
    """Récupère le profil sous forme de lignes pour gr.Dataframe."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT id, prenom, signe, ville, interets, maj FROM profil ORDER BY id ASC"
        )
        lignes = []
        for row in cursor.fetchall():
            lignes.append([
                row["id"],
                row["prenom"] or "",
                row["signe"] or "",
                row["ville"] or "",
                row["interets"] or "",
                convertir_date_client(row["maj"], fuseau=fuseau),
            ])
        return lignes


def charger_notes_tableau(fuseau: Optional[str] = None) -> List[List[Any]]:
    """Récupère les notes sous forme de lignes pour gr.Dataframe."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT id, date, texte FROM notes ORDER BY id DESC LIMIT 50"
        )
        lignes = []
        for row in cursor.fetchall():
            lignes.append([
                row["id"],
                convertir_date_client(row["date"], fuseau=fuseau),
                row["texte"],
            ])
        return lignes


def charger_conversations_tableau(fuseau: Optional[str] = None) -> List[List[Any]]:
    """Récupère l'historique des conversations pour gr.Dataframe."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT id, session, role, contenu, date FROM conversations ORDER BY id DESC LIMIT 100"
        )
        lignes = []
        for row in cursor.fetchall():
            lignes.append([
                row["id"],
                row["session"],
                row["role"],
                row["contenu"],
                convertir_date_client(row["date"], fuseau=fuseau),
            ])
        return lignes


def charger_pense_betes_tableau(fuseau: Optional[str] = None) -> List[List[Any]]:
    """Récupère les pense-bêtes reçus par webhook pour gr.Dataframe."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT id, date, texte, statut FROM pense_betes ORDER BY id DESC LIMIT 50"
        )
        lignes = []
        for row in cursor.fetchall():
            lignes.append([
                row["id"],
                convertir_date_client(row["date"], fuseau=fuseau),
                row["texte"],
                # Le statut en clair : enregistré et en attente, intégré au brief, ou en échec
                LIBELLES_STATUT_PENSE_BETE.get(row["statut"], row["statut"]),
            ])
        return lignes


def rafraichir_memoire(fuseau: Optional[str] = None):
    """Recharge les 4 tableaux de la mémoire."""
    return (
        charger_profil_tableau(fuseau=fuseau),
        charger_notes_tableau(fuseau=fuseau),
        charger_conversations_tableau(fuseau=fuseau),
        charger_pense_betes_tableau(fuseau=fuseau),
    )


def creer_vue_memoire(txt_client_tz: Optional[gr.Textbox] = None):
    """Construit l'onglet Mémoire avec ses composants Gradio.

    Les tableaux démarrent vides : la page les remplit à chaque ouverture. Sinon
    elle embarquerait les valeurs lues au démarrage du serveur, profil compris.

    Returns:
        Un couple (événement, tableaux) :
        - l'événement « effacement confirmé », auquel la page se branche pour vider
          aussi la conversation affichée dans le chat ;
        - la liste des trois tableaux, que la page remplit à son ouverture.
    """
    gr.Markdown(
        """
        ### 🧠 Mémoire persistante de GoodVibe
        *Visualisez en direct et en lecture seule les tables stockées dans `data/agent.db` (heure de votre navigateur).*
        """
    )

    if txt_client_tz is None:
        txt_client_tz = gr.Textbox(value="", visible=False)

    with gr.Row():
        btn_rafraichir = gr.Button("🔄 Rafraîchir la mémoire", variant="secondary")

    gr.Markdown("#### 👤 1. Profil utilisateur (`profil`)")
    df_profil = gr.Dataframe(
        headers=["ID", "Prénom", "Signe", "Ville", "Centres d'intérêt", "Dernière mise à jour (Locale)"],
        interactive=False,
    )

    gr.Markdown("#### 📝 2. Notes personnelles (`notes`)")
    df_notes = gr.Dataframe(
        headers=["ID", "Date (Heure locale)", "Contenu de la note"],
        interactive=False,
    )

    gr.Markdown("#### 💬 3. Historique des échanges (`conversations`)")
    df_conversations = gr.Dataframe(
        headers=["ID", "Session", "Rôle", "Message", "Date (Heure locale)"],
        interactive=False,
    )

    gr.Markdown("#### 📌 4. Pense-bêtes reçus par webhook (`pense_betes`)")
    df_pense_betes = gr.Dataframe(
        headers=["ID", "Date (Heure locale)", "Contenu du pense-bête", "Statut"],
        interactive=False,
    )

    # Zone de purge RGPD "Oublie-moi" avec confirmation
    gr.Markdown("---")
    gr.Markdown("### 🗑️ Gestion de la vie privée (Droit à l'oubli)")
    btn_demander_oubli = gr.Button("🗑️ Oublie-moi (Effacer mes données privées)", variant="stop")

    with gr.Group(visible=False) as zone_confirmation:
        # L'avertissement dit le périmètre réel, le même que le message après l'effacement
        gr.Markdown(f"⚠️ **Attention.** {AVERTISSEMENT_EFFACEMENT}")
        with gr.Row():
            btn_confirmer_oubli = gr.Button("✅ Confirmer la suppression définitive", variant="stop")
            btn_annuler_oubli = gr.Button("❌ Annuler", variant="secondary")

    # Événements interactifs avec détection JS
    def action_actualiser_memoire(fuseau_detecte: str):
        p, n, c, pb = rafraichir_memoire(fuseau=fuseau_detecte)
        return p, n, c, pb, fuseau_detecte

    btn_rafraichir.click(
        fn=action_actualiser_memoire,
        inputs=[txt_client_tz],
        outputs=[df_profil, df_notes, df_conversations, df_pense_betes, txt_client_tz],
        js="""
        (tz) => {
            let clientTz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Paris';
            return [clientTz];
        }
        """,
    )

    txt_client_tz.change(
        fn=action_actualiser_memoire,
        inputs=[txt_client_tz],
        outputs=[df_profil, df_notes, df_conversations, df_pense_betes, txt_client_tz],
    )

    # Affichage de la boîte de confirmation
    btn_demander_oubli.click(
        fn=lambda: gr.update(visible=True),
        inputs=[],
        outputs=[zone_confirmation],
    )

    # Annulation
    btn_annuler_oubli.click(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[zone_confirmation],
    )

    # Confirmation de la suppression
    def executer_oubli(fuseau_detecte: str):
        # Le même effacement, et le même message, que la confirmation faite depuis le chat
        gr.Info(effacer_utilisateur())
        p, n, c, pb = rafraichir_memoire(fuseau=fuseau_detecte)
        return (
            gr.update(visible=False),
            p,
            n,
            c,
            pb,
            fuseau_detecte,
        )

    oubli_confirme = btn_confirmer_oubli.click(
        fn=executer_oubli,
        inputs=[txt_client_tz],
        outputs=[zone_confirmation, df_profil, df_notes, df_conversations, df_pense_betes, txt_client_tz],
    )
    return oubli_confirme, [df_profil, df_notes, df_conversations, df_pense_betes]
