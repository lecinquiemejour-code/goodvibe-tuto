# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Vue de l'activité et de l'observabilité technique de GoodVibe pour Gradio.

Affiche :
- La grille tarifaire officielle en USD, modifiable directement et stockée en base SQLite.
- Les compteurs d'usage du jour et la dernière opération réelle (Chat ou Brief).
- Un tableau du journal d'activité filtrable par identifiant d'exécution.
- Détection automatique du fuseau horaire du navigateur client (JavaScript Intl API).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import gradio as gr

from config import MODELE_IMAGE, MODELE_TEXTE
from db import get_connection, get_tarifs, sauvegarder_tarifs
from tarifs import calculer_cout_usd, formater_cout_usd

logger = logging.getLogger("goodvibe.activite")


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
    """Convertit un timestamp ISO en date/heure du navigateur client (JJ/MM/AAAA HH:MM:SS)."""
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


def extraire_heure_client(date_iso: str, fuseau: Optional[str] = None) -> str:
    """Extrait l'heure du navigateur client au format HH:MM:SS."""
    if not date_iso:
        return ""
    try:
        dt = datetime.fromisoformat(date_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        tz = obtenir_fuseau(fuseau)
        dt_local = dt.astimezone(tz)
        return dt_local.strftime("%H:%M:%S")
    except Exception:
        return ""


def obtenir_statistiques(fuseau: Optional[str] = None) -> Dict[str, Any]:
    """Calcule les statistiques du jour et de la dernière opération pour le navigateur client."""
    tz = obtenir_fuseau(fuseau)
    maintenant_client = datetime.now(tz)
    date_jour_sql = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    date_fr = maintenant_client.strftime("%d/%m/%Y")
    label_aujourdhui = f"Aujourd'hui (depuis 00:00 le {date_fr})"
    tarifs = get_tarifs()

    with get_connection() as conn:
        # Totaux du jour
        cur_jour = conn.execute(
            """
            SELECT
                COUNT(*) as nb_operations,
                SUM(COALESCE(tokens_entree, 0)) as total_entree,
                SUM(COALESCE(tokens_sortie, 0)) as total_sortie,
                SUM(COALESCE(tokens_reflexion, 0)) as total_reflexion
            FROM journal
            WHERE date LIKE ?
            """,
            (f"{date_jour_sql}%",),
        )
        row_jour = cur_jour.fetchone()

        # Comptage des images du jour à part (Feature 10)
        cur_images = conn.execute(
            """
            SELECT COUNT(*) as nb_images
            FROM journal
            WHERE date LIKE ? AND etape = 'image_generation'
            """,
            (f"{date_jour_sql}%",),
        )
        row_images = cur_images.fetchone()
        nb_images_jour = row_images["nb_images"] if row_images else 0

        # Dernière opération ayant consommé des tokens ou généré une image
        cur_derniere = conn.execute(
            """
            SELECT id, date, execution_id, etape, detail,
                   COALESCE(tokens_entree, 0) as tokens_entree,
                   COALESCE(tokens_sortie, 0) as tokens_sortie,
                   COALESCE(tokens_reflexion, 0) as tokens_reflexion
            FROM journal
            WHERE tokens_entree IS NOT NULL OR tokens_sortie IS NOT NULL OR etape = 'image_generation'
            ORDER BY id DESC LIMIT 1
            """
        )
        row_derniere = cur_derniere.fetchone()
        if not row_derniere:
            cur_derniere = conn.execute("SELECT * FROM journal ORDER BY id DESC LIMIT 1")
            row_derniere = cur_derniere.fetchone()

    entree_jour = row_jour["total_entree"] or 0
    sortie_jour = row_jour["total_sortie"] or 0
    reflexion_jour = row_jour["total_reflexion"] or 0
    ops_jour = row_jour["nb_operations"] or 0
    total_tokens_jour = entree_jour + sortie_jour + reflexion_jour
    cout_jour = calculer_cout_usd(
        tokens_entree=entree_jour,
        tokens_sortie=sortie_jour,
        tokens_reflexion=reflexion_jour,
        nb_images=nb_images_jour,
        grille_tarifs=tarifs,
    )

    if row_derniere:
        entree_der = row_derniere["tokens_entree"] or 0
        sortie_der = row_derniere["tokens_sortie"] or 0
        reflexion_der = row_derniere["tokens_reflexion"] or 0
        total_tokens_der = entree_der + sortie_der + reflexion_der
        nb_images_der = 1 if row_derniere["etape"] == "image_generation" else 0
        cout_der = calculer_cout_usd(
            tokens_entree=entree_der,
            tokens_sortie=sortie_der,
            tokens_reflexion=reflexion_der,
            nb_images=nb_images_der,
            grille_tarifs=tarifs,
        )

        heure_der = extraire_heure_client(row_derniere["date"], fuseau=fuseau)

        detail_txt = (row_derniere["detail"] or "").lower()
        etape_txt = (row_derniere["etape"] or "").lower()
        if "brief" in detail_txt or "brief" in etape_txt:
            type_op = "Brief"
        elif "chat" in etape_txt or "conversationnel" in detail_txt:
            type_op = "Chat"
        elif etape_txt == "image_generation":
            type_op = "Illustration"
        else:
            type_op = row_derniere["etape"]

        label_derniere = f"Dernière opération ({type_op}{f' à {heure_der}' if heure_der else ''})"
    else:
        entree_der = sortie_der = reflexion_der = total_tokens_der = 0
        nb_images_der = 0
        cout_der = 0.0
        label_derniere = "Dernière opération (aucune)"

    return {
        "jour": {
            "label": label_aujourdhui,
            "operations": ops_jour,
            "entree": entree_jour,
            "sortie": sortie_jour,
            "reflexion": reflexion_jour,
            "total_tokens": total_tokens_jour,
            "images": nb_images_jour,
            "cout_str": formater_cout_usd(cout_jour),
        },
        "derniere": {
            "label": label_derniere,
            "operations": 1 if row_derniere else 0,
            "entree": entree_der,
            "sortie": sortie_der,
            "reflexion": reflexion_der,
            "total_tokens": total_tokens_der,
            "images": nb_images_der,
            "cout_str": formater_cout_usd(cout_der),
        },
    }


def charger_liste_executions() -> List[str]:
    """Récupère la liste des identifiants d'exécution récents pour le filtre."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT DISTINCT execution_id
            FROM journal
            WHERE execution_id IS NOT NULL AND execution_id != ''
            ORDER BY id DESC
            LIMIT 30
            """
        )
        ids = [row["execution_id"] for row in cursor.fetchall()]
        return ["Toutes les exécutions"] + ids


def charger_lignes_journal(
    filtre_execution: str = "Toutes les exécutions",
    details_techniques: bool = False,
    fuseau: Optional[str] = None,
    limite: int = 50,
) -> Tuple[List[str], List[List[Any]]]:
    """Charge et formate les lignes du journal d'activité à l'heure du navigateur client."""
    query = """
        SELECT id, date, execution_id, agent, etape, detail,
               tokens_entree, tokens_sortie, tokens_reflexion,
               latence_ms, duree_ms
        FROM journal
    """
    params = []
    if filtre_execution and filtre_execution != "Toutes les exécutions":
        query += " WHERE execution_id = ?"
        params.append(filtre_execution)

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limite)

    with get_connection() as conn:
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

    tarifs = get_tarifs()

    if details_techniques:
        headers = [
            "ID",
            "Date (Heure locale)",
            "Exécution",
            "Agent",
            "Étape",
            "Tokens Entrée",
            "Tokens Sortie",
            "Tokens Réflexion",
            "Latence (ms)",
            "Durée (ms)",
            "Coût estimé (USD)",
            "Détail technique",
        ]
    else:
        headers = [
            "ID",
            "Date (Heure locale)",
            "Étape",
            "Tokens Entrée",
            "Tokens Sortie",
            "Tokens Réflexion",
            "Latence (ms)",
            "Durée (ms)",
            "Coût estimé (USD)",
        ]

    lignes = []
    for r in rows:
        entree = r["tokens_entree"] or 0
        sortie = r["tokens_sortie"] or 0
        reflexion = r["tokens_reflexion"] or 0
        est_image = (r["etape"] == "image_generation")
        cout = calculer_cout_usd(
            tokens_entree=entree,
            tokens_sortie=sortie,
            tokens_reflexion=reflexion,
            nb_images=1 if est_image else 0,
            grille_tarifs=tarifs,
        )
        cout_str = formater_cout_usd(cout) if (entree or sortie or reflexion or est_image) else "-"

        # Conversion à l'heure du navigateur client
        date_locale = convertir_date_client(r["date"], fuseau=fuseau)

        if details_techniques:
            lignes.append([
                r["id"],
                date_locale,
                r["execution_id"] or "-",
                r["agent"],
                r["etape"],
                entree if entree > 0 else "-",
                sortie if sortie > 0 else "-",
                reflexion if reflexion > 0 else "-",
                f"{r['latence_ms']} ms" if r["latence_ms"] is not None else "-",
                f"{r['duree_ms']} ms" if r["duree_ms"] is not None else "-",
                cout_str,
                r["detail"] or "",
            ])
        else:
            lignes.append([
                r["id"],
                date_locale,
                r["etape"],
                entree if entree > 0 else "-",
                sortie if sortie > 0 else "-",
                reflexion if reflexion > 0 else "-",
                f"{r['latence_ms']} ms" if r["latence_ms"] is not None else "-",
                f"{r['duree_ms']} ms" if r["duree_ms"] is not None else "-",
                cout_str,
            ])

    return headers, lignes


def generer_markdown_statistiques(fuseau: Optional[str] = None) -> str:
    """Génère l'affichage synthétique des compteurs sous forme de tableau Markdown."""
    stats = obtenir_statistiques(fuseau=fuseau)
    j = stats["jour"]
    d = stats["derniere"]

    return f"""
| Période / Événement | Opérations | Tokens Entrée | Tokens Sortie | Réflexion | Total Tokens | Images | Coût estimé (USD) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **{j['label']}** | {j['operations']} | {j['entree']:,} | {j['sortie']:,} | {j['reflexion']:,} | **{j['total_tokens']:,}** | {j['images']} | **{j['cout_str']}** |
| **{d['label']}** | {d['operations']} | {d['entree']:,} | {d['sortie']:,} | {d['reflexion']:,} | **{d['total_tokens']:,}** | {d['images']} | **{d['cout_str']}** |
"""


def creer_vue_activite(txt_client_tz: Optional[gr.Textbox] = None):
    """Construit l'onglet Activité avec détection automatique du fuseau client."""
    gr.Markdown(
        """
        ### 📊 Observabilité & Journal d'activité
        *Mesurez en temps réel la consommation de tokens, les temps de réponse et le coût estimé en USD (heure de votre navigateur).*
        """
    )

    if txt_client_tz is None:
        txt_client_tz = gr.Textbox(value="", visible=False)

    with gr.Row():
        btn_rafraichir = gr.Button("🔄 Rafraîchir l'activité", variant="secondary")

    gr.Markdown("#### 📈 Compteurs d'usage & Dépenses estimées")
    md_stats = gr.Markdown(value=lambda: generer_markdown_statistiques())

    # Section de configuration et visualisation claire des tarifs en base SQLite.
    # Une base neuve n'a aucun prix : les champs démarrent vides, et le pilote les remplit.
    tarifs_actuels = get_tarifs() or {}
    with gr.Accordion("⚙️ Grille tarifaire appliquée (stockée dans la base SQLite)", open=True):
        gr.Markdown(
            f"""
            - **Modèle texte en cours** : `{MODELE_TEXTE}`
            - **Modèle image en cours** : `{MODELE_IMAGE}`
            - **Tarifs officiels Google AI** : [https://ai.google.dev/gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing)

            *GoodVibe ne connaît aucun prix d'avance : relevez ceux de vos deux modèles sur la page ci-dessus et saisissez-les ci-dessous, par million de tokens pour le texte et par unité pour l'image (USD), puis enregistrez. Tant que la grille est vide, aucun coût n'est estimé.*
            """
        )
        with gr.Row():
            num_prix_entree = gr.Number(
                label="Entrée ($ / 1M tokens)",
                value=tarifs_actuels.get("prix_entree_usd"),
                step=0.01,
            )
            num_prix_sortie = gr.Number(
                label="Sortie ($ / 1M tokens)",
                value=tarifs_actuels.get("prix_sortie_usd"),
                step=0.01,
            )
            num_prix_reflexion = gr.Number(
                label="Réflexion ($ / 1M tokens)",
                value=tarifs_actuels.get("prix_reflexion_usd"),
                step=0.01,
            )
            num_prix_image = gr.Number(
                label="Image ($ / unité)",
                value=tarifs_actuels.get("prix_image_usd"),
                step=0.0001,
            )
        btn_sauvegarder_tarifs = gr.Button("💾 Enregistrer la nouvelle grille tarifaire", variant="primary")

    gr.Markdown("#### 📋 Journal des exécutions")
    with gr.Row():
        liste_initiale = charger_liste_executions()
        dropdown_filtre = gr.Dropdown(
            choices=liste_initiale,
            value=liste_initiale[0],
            label="Filtrer par exécution",
            scale=3,
        )
        cb_details = gr.Checkbox(
            label="🔬 Afficher les détails techniques (ID, agent, logs)",
            value=False,
            scale=2,
        )

    headers_init, lignes_init = charger_lignes_journal(
        filtre_execution=liste_initiale[0],
        details_techniques=False,
    )
    df_journal = gr.Dataframe(
        headers=headers_init,
        value=lignes_init,
        interactive=False,
    )

    def actualiser_tout(filtre: str, details: bool, fuseau_detecte: str):
        new_stats = generer_markdown_statistiques(fuseau=fuseau_detecte)
        new_choices = charger_liste_executions()
        h, lignes = charger_lignes_journal(filtre_execution=filtre, details_techniques=details, fuseau=fuseau_detecte)
        choix_valide = filtre if filtre in new_choices else new_choices[0]
        return (
            new_stats,
            gr.update(choices=new_choices, value=choix_valide),
            gr.update(headers=h, value=lignes),
            fuseau_detecte,
        )

    def filtrer_tableau(filtre: str, details: bool, fuseau_detecte: str):
        h, lignes = charger_lignes_journal(filtre_execution=filtre, details_techniques=details, fuseau=fuseau_detecte)
        return gr.update(headers=h, value=lignes)

    def action_enregistrer_tarifs(p_entree, p_sortie, p_refl, p_img, filtre, details, fuseau_detecte):
        # Les quatre prix sont obligatoires : un champ vide n'est remplacé par aucune valeur
        if None in (p_entree, p_sortie, p_refl, p_img):
            logger.info("Grille de prix incomplète : rien n'est enregistré")
            gr.Warning("Grille incomplète : saisissez les quatre prix avant d'enregistrer.")
        else:
            sauvegarder_tarifs(
                prix_entree_usd=float(p_entree),
                prix_sortie_usd=float(p_sortie),
                prix_reflexion_usd=float(p_refl),
                prix_image_usd=float(p_img),
            )
            logger.info("Grille de prix enregistrée")
            gr.Info("Grille tarifaire enregistrée avec succès dans la base SQLite !")
        new_stats = generer_markdown_statistiques(fuseau=fuseau_detecte)
        h, lignes = charger_lignes_journal(filtre_execution=filtre, details_techniques=details, fuseau=fuseau_detecte)
        return (
            new_stats,
            gr.update(headers=h, value=lignes),
            fuseau_detecte,
        )

    # Détection JS automatique lors du clic sur Rafraîchir
    btn_rafraichir.click(
        fn=actualiser_tout,
        inputs=[dropdown_filtre, cb_details, txt_client_tz],
        outputs=[md_stats, dropdown_filtre, df_journal, txt_client_tz],
        js="""
        (filtre, details, tz) => {
            let clientTz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Paris';
            return [filtre, details, clientTz];
        }
        """,
    )

    dropdown_filtre.change(
        fn=filtrer_tableau,
        inputs=[dropdown_filtre, cb_details, txt_client_tz],
        outputs=[df_journal],
    )

    cb_details.change(
        fn=filtrer_tableau,
        inputs=[dropdown_filtre, cb_details, txt_client_tz],
        outputs=[df_journal],
    )

    btn_sauvegarder_tarifs.click(
        fn=action_enregistrer_tarifs,
        inputs=[num_prix_entree, num_prix_sortie, num_prix_reflexion, num_prix_image, dropdown_filtre, cb_details, txt_client_tz],
        outputs=[md_stats, df_journal, txt_client_tz],
        js="""
        (p1, p2, p3, p4, filtre, details, tz) => {
            let clientTz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Paris';
            return [p1, p2, p3, p4, filtre, details, clientTz];
        }
        """,
    )

    # Mise à jour automatique dès que le fuseau est détecté au chargement
    txt_client_tz.change(
        fn=actualiser_tout,
        inputs=[dropdown_filtre, cb_details, txt_client_tz],
        outputs=[md_stats, dropdown_filtre, df_journal, txt_client_tz],
    )
