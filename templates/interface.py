# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Interface web de GoodVibe (Gradio) — Feature 2.

Propose une interface conviviale accessible dans le navigateur, protégée
par mot de passe, avec chat en streaming, persistance et rechargement
de l'historique des conversations, et structure d'onglets pour accueillir
les futures fonctionnalités (brief, mémoire, activité).
"""

import logging
import sys
from typing import Any, Dict, Generator, List, Tuple

import gradio as gr

from agent import repondre
from brief import generer_brief_complet_stream
from config import (
    DOSSIER_IMAGES,
    PORT_GRADIO,
    WEB_PASSWORD,
    WEB_USER,
    verifier_acces_web,
    verifier_config,
)
from db import charger_historique, get_dernier_brief, oubli_en_cours, sauvegarder_message
from fragments import FLUX, REPONSE, Fragment, ajouter_au_flux, copier_flux
from image import get_image_du_jour
from vue_activite import creer_vue_activite
from vue_memoire import creer_vue_memoire, rafraichir_memoire

logger = logging.getLogger("goodvibe.interface")


def extraire_texte(contenu: Any) -> str:
    """Ramène le contenu d'un message de Gradio à un texte simple.

    Gradio livre chaque message de l'historique comme une liste de morceaux
    (ex : [{'text': 'salut', 'type': 'text'}]) ; la base le livre comme un texte.

    Args:
        contenu: Le contenu du message, texte ou liste de morceaux.

    Returns:
        Le texte seul ; une chaîne vide si le contenu n'en comporte pas.
    """
    if isinstance(contenu, str):
        return contenu
    if isinstance(contenu, dict):
        contenu = [contenu]
    if isinstance(contenu, list):
        morceaux = []
        for morceau in contenu:
            if isinstance(morceau, str):
                morceaux.append(morceau)
            elif isinstance(morceau, dict) and morceau.get("type") == "text":
                morceaux.append(morceau.get("text", ""))
        return "\n".join(morceaux)
    return ""


def preparer_historique(history: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Ramène l'historique affiché par Gradio au seul dialogue, en texte simple.

    Les coulisses et le relevé sont des messages marqués d'un titre (metadata.title) :
    on les écarte sur cette marque, sans lire leur texte.

    Args:
        history: L'historique tel que Gradio le transmet.

    Returns:
        Les messages du dialogue, sous la forme {"role", "content"}.
    """
    dialogue = []
    for message in history:
        if (message.get("metadata") or {}).get("title"):
            continue
        texte = extraire_texte(message.get("content", "")).strip()
        if texte:
            dialogue.append({"role": message.get("role", "user"), "content": texte})
    # Journalisation des quantités uniquement : jamais le contenu des messages
    logger.info("Historique préparé : %d message(s) affiché(s), %d retenu(s)", len(history), len(dialogue))
    return dialogue


def en_message(fragment: Fragment) -> gr.ChatMessage:
    """Transforme un fragment de coulisses ou de relevé en message marqué pour Gradio.

    Args:
        fragment: Le fragment à afficher.

    Returns:
        Un message dont le titre sert de marque : Gradio l'affiche en bloc repliable.
    """
    # Le relevé tient en une ligne : son titre porte les chiffres, son contenu est vide
    titre = fragment.titre or fragment.texte
    contenu = fragment.texte if fragment.titre else ""
    marque: Dict[str, Any] = {"title": titre}
    if fragment.replie:
        marque["status"] = "done"  # bloc affiché replié
    return gr.ChatMessage(role="assistant", content=contenu, metadata=marque)


def chat_stream(
    message: str, history: list, voir_reflexion: bool = False
) -> Generator[Tuple[List[gr.ChatMessage], bool, Dict[str, List[Any]]], None, None]:
    """Relaye les fragments de l'agent vers l'interface Gradio.

    Args:
        message: La saisie de l'utilisateur.
        history: L'historique des messages précédents au format Gradio.
        voir_reflexion: Si True, affiche les coulisses (résumé de réflexion et outils)
            et remplit le panneau du flux brut.

    Yields:
        Un triplet (messages, oubli, flux) :
        - la liste des messages de la réponse en cours : les coulisses et le relevé
          en messages marqués, le texte de la réponse en message simple ;
        - un signal, vrai en fin de réponse si l'utilisateur vient d'être oublié ;
        - les événements bruts reçus de Gemini pour cette réponse, rangés par tour :
          ils vont dans leur panneau, jamais dans le chat.
    """
    messages: List[gr.ChatMessage] = []
    texte_reponse = ""
    reponse_en_cours = False  # vrai tant que le dernier message est celui de la réponse
    # Le flux repart de zéro à chaque message : le panneau montre la réponse en cours
    flux_recu: Dict[str, List[Any]] = {}

    dialogue = preparer_historique(history)
    fragments = repondre(
        message,
        historique=dialogue,
        voir_reflexion=voir_reflexion,
        voir_flux=voir_reflexion,
    )
    for fragment in fragments:
        if fragment.nature == FLUX:
            # L'événement brut rejoint son panneau : il ne crée aucun message dans le
            # chat, et ne coupe pas la réponse en cours d'écriture.
            ajouter_au_flux(flux_recu, fragment)
        elif fragment.nature == REPONSE:
            texte_reponse += fragment.texte
            if reponse_en_cours:
                # On remplace le dernier message par sa version allongée
                contenu = messages[-1].content + fragment.texte
                messages[-1] = gr.ChatMessage(role="assistant", content=contenu)
            else:
                messages.append(gr.ChatMessage(role="assistant", content=fragment.texte))
                reponse_en_cours = True
        else:
            messages.append(en_message(fragment))
            reponse_en_cours = False
        yield list(messages), False, copier_flux(flux_recu)

    # Journalisation des quantités uniquement : jamais le contenu des événements
    logger.info(
        "Flux brut affiché : %d événement(s) sur %d tour(s)",
        sum(len(evenements) for evenements in flux_recu.values()),
        len(flux_recu),
    )

    # L'outil d'oubli a-t-il effacé les données pendant cet échange ? On le lit avant
    # la sauvegarde, qui désarme le verrou.
    if oubli_en_cours():
        logger.info("Oubli demandé dans le chat : la conversation affichée sera vidée")
        yield list(messages), True, copier_flux(flux_recu)

    # Enregistrement de l'échange dans la table conversations : le message et le texte
    # de la réponse, jamais les coulisses ni le relevé.
    try:
        sauvegarder_message(role="user", contenu=message)
        sauvegarder_message(role="assistant", contenu=texte_reponse.strip())
        logger.info("Échange enregistré (%d caractères de réponse)", len(texte_reponse))
    except Exception as e:
        logger.warning("Échec de sauvegarde du message : %s", e)


MESSAGE_SANS_BRIEF = (
    "*Aucun brief produit pour le moment. Cliquez sur le bouton ci-dessus "
    "pour générer votre premier brief !*"
)


def charger_page() -> tuple:
    """Relit la base à chaque ouverture de la page.

    La page ne garde aucune photographie prise au démarrage du serveur : sinon une
    conversation effacée par « Oublie-moi » réapparaîtrait au rechargement, et
    repartirait au modèle au message suivant.

    Returns:
        L'historique pour l'affichage du chat, le même pour les deux mémoires internes
        du composant de chat, la mise à jour de l'image, et le texte du brief.
    """
    historique = charger_historique()
    dernier = get_dernier_brief()
    texte_brief = dernier["contenu"] if dernier else MESSAGE_SANS_BRIEF
    image = get_image_du_jour()
    # Journalisation des quantités uniquement : jamais le contenu
    logger.info(
        "Page ouverte : %d message(s) relu(s), brief %s, image %s",
        len(historique),
        "présent" if dernier else "absent",
        "présente" if image else "absente",
    )
    return historique, historique, historique, gr.update(value=image, visible=bool(image)), texte_brief


def vider_chat() -> tuple:
    """Vide l'affichage du chat et ses deux mémoires internes, après un « Oublie-moi »."""
    logger.info("Chat vidé après effacement des données")
    return [], [], []


def garder_la_confirmation(oubli: bool, affichage: List[Dict[str, Any]]) -> tuple:
    """Après un oubli demandé dans le chat, ne laisse à l'écran que la confirmation.

    Sans cela, la conversation effacée de la base resterait affichée, et repartirait
    au modèle au message suivant.

    Args:
        oubli: Le signal rendu par chat_stream en fin de réponse.
        affichage: La conversation affichée, au format Gradio.

    Returns:
        L'affichage du chat, ses deux mémoires internes, et le signal remis à faux.
    """
    if not oubli:
        return gr.skip(), gr.skip(), gr.skip(), False
    # La confirmation est la dernière réponse de GoodVibe : un message sans titre
    reponses = [
        m for m in affichage
        if m.get("role") == "assistant" and not (m.get("metadata") or {}).get("title")
    ]
    confirmation = reponses[-1:]
    logger.info("Conversation vidée après oubli : %d message(s) gardé(s)", len(confirmation))
    return confirmation, confirmation, confirmation, False


CSS_INTERFACE = """
hr {
    margin: 8px 0 !important;
    border: none;
    border-top: 1px solid #e5e7eb;
}
.zone-brief-contenu {
    margin-top: 16px;
    padding-top: 8px;
}
/* Deux zones côte à côte (le chat ou le brief à gauche, le flux brut à droite), séparées
   par une barre qu'on tire à la souris. La page est pensée pour un écran d'ordinateur :
   les deux zones ne s'empilent jamais. Chaque règle commence par .gradio-container pour
   passer avant les styles que Gradio pose lui-même sur ses boîtes. */
.gradio-container .zone-deux-colonnes {
    flex-wrap: nowrap !important;
}
.gradio-container .zone-deux-colonnes .colonne-gauche,
.gradio-container .zone-deux-colonnes .colonne-droite {
    min-width: 0 !important;
}
/* La barre, c'est la boîte (.block) seule. Gradio recopie la classe sur le contenu de la
   boîte et rend la boîte transparente : on impose donc la couleur à la boîte, et on
   cache son contenu, qui ne sert qu'à la faire exister. */
.gradio-container .block.barre-separation {
    flex: 0 0 10px !important;
    min-width: 10px !important;
    width: 10px;
    padding: 0 !important;
    border: none !important;
    border-radius: 5px !important;
    background: #e5e7eb !important;
    cursor: col-resize;
    align-self: stretch;
    touch-action: none;
}
.gradio-container .block.barre-separation:hover,
.gradio-container .block.barre-separation.en-cours {
    background: #f97316 !important;
}
.gradio-container .block.barre-separation .html-container {
    display: none;
}
/* Un seul ascenseur vertical pour le flux. Gradio donne à la boîte du composant JSON une
   hauteur maximale et un ascenseur, et à la zone du JSON qu'elle contient un second
   ascenseur : on retire celui de la boîte, et la hauteur se règle sur la zone du JSON.
   Le titre et le bouton « copier » restent ainsi en place quand le flux défile. */
.gradio-container .flux-brut {
    max-height: none !important;
    overflow: hidden !important;
}
.gradio-container .flux-brut .json-holder {
    max-height: 65vh !important;
    overflow-y: auto;
}
"""

# La barre de séparation : tant qu'on la tient, la largeur de la zone de gauche suit la
# souris, et le flux brut prend la place qui reste. Le même code sert aux deux onglets :
# il part de la barre saisie et cherche les deux zones qui l'entourent. Rien n'est
# mémorisé : la page rechargée retrouve ses largeurs de départ. Les écoutes sont posées
# sur le document, pour continuer de suivre la souris quand elle sort de la barre.
LARGEUR_MINI_ZONE = 280  # en pixels : aucune des deux zones ne devient plus étroite
JS_BARRE_SEPARATION = """
() => {
    const MINI = %d;
    let enCours = null;
    document.addEventListener('pointerdown', (e) => {
        const barre = e.target.closest('.block.barre-separation');
        if (!barre) return;
        const zone = barre.closest('.zone-deux-colonnes');
        if (!zone) return;
        const gauche = zone.querySelector('.colonne-gauche');
        const droite = zone.querySelector('.colonne-droite');
        if (!gauche || !droite) return;
        // On retient le point de départ : la largeur suivra le déplacement de la souris,
        // pour que la barre reste sous le curseur quelles que soient les marges de la page.
        enCours = {
            barre, zone, gauche, droite,
            xDepart: e.clientX,
            largeurDepart: gauche.getBoundingClientRect().width,
        };
        barre.classList.add('en-cours');
        document.body.style.userSelect = 'none';
        document.body.style.cursor = 'col-resize';
        e.preventDefault();
        console.log('[SEPARATION] début du réglage');
    });
    document.addEventListener('pointermove', (e) => {
        if (!enCours) return;
        const cadre = enCours.zone.getBoundingClientRect();
        const voulue = enCours.largeurDepart + (e.clientX - enCours.xDepart);
        const largeur = Math.min(Math.max(voulue, MINI), cadre.width - MINI);
        enCours.gauche.style.flex = `0 0 ${largeur}px`;
        enCours.droite.style.flex = '1 1 0';
    });
    const finir = () => {
        if (!enCours) return;
        console.log('[SEPARATION] fin du réglage, zone de gauche :', enCours.gauche.style.flex);
        enCours.barre.classList.remove('en-cours');
        enCours = null;
        document.body.style.userSelect = '';
        document.body.style.cursor = '';
    };
    document.addEventListener('pointerup', finir);
    document.addEventListener('pointercancel', finir);
}
""" % LARGEUR_MINI_ZONE

# Le suivi du flux : à chaque événement ajouté au panneau, son ascenseur redescend tout en
# bas, pour voir le flux arriver. Le suivi est forcé (choix de conception) : il ne s'arrête pas
# si on remonte pendant la réception. Une fois la réponse finie, plus rien n'arrive, et on
# lit le panneau librement. Le marqueur {id} est remplacé par l'identifiant du panneau.
JS_SUIVRE_LE_FLUX = """
() => {
    // On laisse à la page le temps de dessiner le nouvel événement avant de descendre
    requestAnimationFrame(() => {
        const zone = document.querySelector('#{id} .json-holder');
        if (zone) zone.scrollTop = zone.scrollHeight;
    });
}
"""


def creer_panneau_flux(titre: str, identifiant: str) -> gr.JSON:
    """Crée un panneau du flux brut, sans le placer dans la page.

    Chaque événement reçu de Gemini s'y affiche tel quel, dans une arborescence qu'on
    plie, qu'on déplie et qu'on copie en un clic. L'appelant le place avec .render(),
    puis appelle suivre_le_flux() : le panneau doit être dans la page pour être écouté.

    Args:
        titre: Le titre affiché en haut du panneau.
        identifiant: L'identifiant du panneau dans la page, unique par onglet.

    Returns:
        Le composant JSON, à placer dans la colonne de droite.
    """
    return gr.JSON(
        label=titre,
        open=True,
        elem_id=identifiant,
        elem_classes=["flux-brut"],
        render=False,
    )


def suivre_le_flux(panneau: gr.JSON) -> None:
    """Fait redescendre l'ascenseur d'un panneau à chaque événement qui s'y ajoute.

    Args:
        panneau: Un panneau du flux brut, déjà placé dans la page.
    """
    panneau.change(
        fn=None,
        inputs=[],
        outputs=[],
        js=JS_SUIVRE_LE_FLUX.replace("{id}", str(panneau.elem_id)),
    )


def creer_barre_separation() -> gr.HTML:
    """Place la barre qu'on tire à la souris pour régler la largeur des deux zones.

    Returns:
        Le composant de la barre, placé entre la colonne de gauche et celle de droite.
    """
    return gr.HTML(
        value="<div>&nbsp;</div>",
        elem_classes=["barre-separation"],
        container=False,
        padding=False,
        min_width=10,
    )


def creer_interface() -> gr.Blocks:
    """Construit la structure de l'interface Gradio avec ses onglets."""
    with gr.Blocks(title="GoodVibe — Assistant personnel") as demo:
        # Composant invisible stockant le fuseau horaire réel du navigateur client
        txt_client_tz = gr.Textbox(value="Europe/Paris", visible=False, elem_id="client_timezone")

        with gr.Row():
            gr.Markdown(
                """
                # ☀️ GoodVibe — Votre assistant personnel du matin
                *Discutez avec votre agent, observez ses réponses en direct et préparez votre journée.*
                """
            )
            # La déconnexion passe par l'adresse /logout, fournie par Gradio dès que la page
            # est protégée par un mot de passe. Elle ferme toutes les sessions de l'identifiant.
            gr.Button("🚪 Se déconnecter", link="/logout", variant="secondary", scale=0, min_width=180)

        with gr.Tabs():
            with gr.Tab("💬 Chat"):
                cb_reflexion = gr.Checkbox(
                    label="🧠 Voir les coulisses (réflexion, outils & JSON)",
                    value=True,
                )
                # Le panneau du flux brut est créé ici, avant le chat qui le remplit, et
                # placé plus bas, dans la colonne de droite.
                json_flux = creer_panneau_flux(
                    "📥 Flux brut reçu de Google Gemini (réponse en cours)", "flux-brut-chat"
                )
                # Deux colonnes côte à côte : la page est pensée pour un écran d'ordinateur
                with gr.Row(elem_classes=["zone-deux-colonnes"]):
                    with gr.Column(scale=3, elem_classes=["colonne-gauche"]):
                        # Le chat démarre vide : charger_page() le remplit depuis la base
                        # à chaque ouverture de la page (voir demo.load plus bas).
                        chatbot = gr.Chatbot()
                        # Signal rendu par chat_stream : vrai quand l'utilisateur vient d'être oublié
                        signal_oubli = gr.State(False)
                        chat = gr.ChatInterface(
                            fn=chat_stream,
                            chatbot=chatbot,
                            textbox=gr.Textbox(placeholder="Posez votre question à GoodVibe..."),
                            additional_inputs=[cb_reflexion],
                            additional_outputs=[signal_oubli, json_flux],
                        )
                    creer_barre_separation()
                    with gr.Column(scale=2, elem_classes=["colonne-droite"]):
                        json_flux.render()
                suivre_le_flux(json_flux)
                signal_oubli.change(
                    fn=garder_la_confirmation,
                    inputs=[signal_oubli, chatbot],
                    outputs=[chatbot, chat.chatbot_state, chat.chatbot_value, signal_oubli],
                )

            with gr.Tab("📰 Brief du jour"):
                gr.Markdown("### 🌅 Votre brief matinal")
                btn_generer = gr.Button("☀️ Générer le brief maintenant", variant="primary")

                json_flux_brief = creer_panneau_flux(
                    "📥 Flux brut reçu de Google Gemini (rédaction du brief)", "flux-brut-brief"
                )
                # Même disposition que le chat : le brief à gauche, le flux brut à droite
                with gr.Row(elem_classes=["zone-deux-colonnes"]):
                    with gr.Column(scale=3, elem_classes=["colonne-gauche"]):
                        # Le brief et l'image démarrent vides : charger_page() les relit à chaque ouverture
                        md_brief = gr.Markdown(value=MESSAGE_SANS_BRIEF, elem_classes=["zone-brief-contenu"])

                        # Composant d'illustration quotidienne (Feature 10 : affiché en bas sous le texte du brief)
                        img_brief = gr.Image(
                            value=None,
                            label="Illustration du jour",
                            type="filepath",
                            interactive=False,
                            visible=False,
                            height=360,
                        )
                    creer_barre_separation()
                    with gr.Column(scale=2, elem_classes=["colonne-droite"]):
                        json_flux_brief.render()
                suivre_le_flux(json_flux_brief)

                def action_generer_brief() -> Generator[tuple, None, None]:
                    gr.Info("☀️ GoodVibe s'active : génération de l'illustration et du brief...")
                    # Le bouton de la page demande le flux brut : il a un panneau pour l'afficher.
                    # Le brief automatique du matin ne le demande pas.
                    etapes = generer_brief_complet_stream(forcer=True, voir_flux=True, declencheur="bouton")
                    for chemin_img, texte, flux in etapes:
                        if chemin_img:
                            yield gr.update(value=chemin_img, visible=True), texte, flux
                        else:
                            yield gr.update(value=None, visible=False), texte, flux

                btn_generer.click(
                    fn=action_generer_brief,
                    inputs=[],
                    outputs=[img_brief, md_brief, json_flux_brief],
                )

            with gr.Tab("🧠 Mémoire"):
                oubli_confirme, tableaux_memoire = creer_vue_memoire(txt_client_tz=txt_client_tz)
                # Après un « Oublie-moi », la conversation affichée est vidée elle aussi :
                # sinon elle repartirait au modèle au message suivant.
                oubli_confirme.then(
                    fn=vider_chat,
                    inputs=[],
                    outputs=[chatbot, chat.chatbot_state, chat.chatbot_value],
                )

            with gr.Tab("📊 Activité"):
                creer_vue_activite(txt_client_tz=txt_client_tz)

        # Relecture de la base à chaque ouverture de la page
        demo.load(
            fn=charger_page,
            inputs=[],
            outputs=[chatbot, chat.chatbot_state, chat.chatbot_value, img_brief, md_brief],
        )
        # Les tableaux de l'onglet Mémoire sont remplis de la même façon
        demo.load(
            fn=rafraichir_memoire,
            inputs=[txt_client_tz],
            outputs=tableaux_memoire,
        )

        # Mise en service de la barre de séparation à l'ouverture de la page
        demo.load(fn=None, inputs=[], outputs=[], js=JS_BARRE_SEPARATION)

        # Détection automatique du fuseau horaire du navigateur client à l'ouverture de la page
        demo.load(
            fn=None,
            inputs=[],
            outputs=[txt_client_tz],
            js="() => Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Paris'",
        )

    return demo


def main():
    """Point d'entrée du serveur web."""
    try:
        verifier_config()
        verifier_acces_web()
    except ValueError as e:
        print(f"\n[Configuration incomplète]\n{e}\n")
        sys.exit(1)

    demo = creer_interface()
    print(f"\n[Serveur web GoodVibe démarré sur http://localhost:{PORT_GRADIO}]")
    print(f"Identifiant : {WEB_USER}")

    demo.launch(
        # Écoute sur la machine seule : sur le serveur, seul Caddy (même machine) atteint la page,
        # toujours en HTTPS ; en local, le navigateur est sur la même machine.
        server_name="127.0.0.1",
        server_port=PORT_GRADIO,
        auth=(WEB_USER, WEB_PASSWORD),
        allowed_paths=[str(DOSSIER_IMAGES)],
        show_error=True,
        # Depuis Gradio 6, la mise en forme se passe au lancement, et non plus à gr.Blocks() :
        # l'ancienne place est périmée et disparaîtra (d'où gradio>=6.0.0 dans requirements.txt).
        css=CSS_INTERFACE,
    )


if __name__ == "__main__":
    main()
