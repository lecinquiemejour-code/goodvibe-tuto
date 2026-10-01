# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Fixtures globales pour la suite de tests GoodVibe (Feature 11).

Garanties fondamentales :
1. Isolation totale de la base de données : chaque test s'exécute sur une base SQLite
   en mémoire partagée fraîchement initialisée, sans jamais modifier ni écraser data/agent.db.
2. Zéro appel réseau : toutes les connexions sortantes (Google GenAI, Open-Meteo, MCP fetch)
   sont simulées et interceptées. Le serveur MCP n'est jamais lancé : sa liste d'outils
   est simulée pour tous les tests.
"""

import json
import sqlite3
import uuid
from typing import Any, Dict, List, Optional, Tuple

import pytest

import config
import db

# ============================================================================
# 1. FIXTURE DE BASE DE DONNÉES EN MÉMOIRE
# ============================================================================

@pytest.fixture(autouse=True)
def base_sqlite_memoire(monkeypatch, tmp_path):
    """Crée une base SQLite isolée en mémoire partagée pour chaque test.

    Toutes les tables sont créées à l'identique de la production,
    sans laisser aucune trace dans le dossier data/ du projet.
    """
    nom_base = f"goodvibe_test_{uuid.uuid4().hex}"
    uri_memoire = f"file:{nom_base}?mode=memory&cache=shared"

    # Connexion gardienne maintenant la base en mémoire active pendant toute la durée du test
    conn_gardienne = sqlite3.connect(uri_memoire, uri=True)

    # Redirection de DB_PATH dans le module db
    monkeypatch.setattr(db, "DB_PATH", uri_memoire)

    # Redirection du dossier images vers un répertoire temporaire
    dossier_images_test = tmp_path / "images"
    dossier_images_test.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "DOSSIER_IMAGES", dossier_images_test)

    import image
    monkeypatch.setattr(image, "DOSSIER_IMAGES", dossier_images_test)

    # Initialisation du schéma complet en mémoire
    db.initialiser()

    # La demande de suppression en attente est une variable du module : on la vide,
    # pour qu'un test ne trouve pas la demande déposée par un autre.
    import confirmation
    monkeypatch.setattr(confirmation, "_demande_en_attente", None)

    yield conn_gardienne

    # Nettoyage et libération de la mémoire
    conn_gardienne.close()


# ============================================================================
# 1 bis. FIXTURE DU SERVEUR MCP SIMULÉ
# ============================================================================

# Ce que le serveur fetch annoncerait par list_tools, une fois converti pour Gemini
FAUX_OUTIL_FETCH = {
    "type": "function",
    "name": "fetch",
    "description": "Fetches a URL from the internet (description annoncée par le faux serveur).",
    "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
}


@pytest.fixture(autouse=True)
def faux_serveur_mcp(monkeypatch):
    """Remplace la liste des outils du serveur MCP par une liste simulée.

    Sans cette fixture, chaque appel à la boucle d'agent lancerait le vrai serveur
    fetch par uvx : les tests seraient lents, et échoueraient là où uvx est absent.
    """
    import mcp_client
    import outils

    monkeypatch.setattr(outils, "lister_outils_mcp", lambda: [dict(FAUX_OUTIL_FETCH)])
    # La liste retenue par le client est une variable du module : on la vide,
    # pour qu'un test ne reçoive pas la liste obtenue par un autre.
    monkeypatch.setattr(mcp_client, "_outils_en_memoire", None)


# ============================================================================
# 2. CLASSES DE SIMULATION DU CLIENT GOOGLE GENAI
# ============================================================================

class MockUsage:
    """Simule les métriques d'utilisation officielles de l'API Interactions."""
    def __init__(self, input_tokens: int = 120, output_tokens: int = 45, thought_tokens: int = 15):
        self.total_input_tokens = input_tokens
        self.total_output_tokens = output_tokens
        self.total_thought_tokens = thought_tokens


class MockInteraction:
    """Simule un objet Interaction retourné par le flux streaming de Gemini."""
    def __init__(self, interaction_id: str = "inter_test_123", usage: Optional[MockUsage] = None):
        self.id = interaction_id
        self.usage = usage or MockUsage()


class MockStep:
    """Simule une étape de l'API Interactions (ex: function_call)."""
    def __init__(self, step_type: str = "function_call", step_id: str = "call_abc", name: str = "meteo"):
        self.type = step_type
        self.id = step_id
        self.name = name


class MockDeltaContent:
    def __init__(self, text: str = ""):
        self.text = text


class MockDelta:
    """Simule un fragment de delta reçu dans l'événement de stream."""
    def __init__(
        self,
        delta_type: str = "text",
        text: Optional[str] = None,
        arguments: Optional[str] = None,
        content: Optional[MockDeltaContent] = None,
    ):
        self.type = delta_type
        self.text = text
        self.arguments = arguments
        self.content = content


def _en_dictionnaire(objet: Any) -> Any:
    """Convertit un objet simulé en dictionnaire, sans ses champs vides."""
    if hasattr(objet, "__dict__"):
        return {cle: _en_dictionnaire(v) for cle, v in vars(objet).items() if v is not None}
    return objet


class MockEvent:
    """Simule un événement unitaire de stream d'interaction."""
    def __init__(
        self,
        event_type: Optional[str] = None,
        interaction: Optional[MockInteraction] = None,
        step: Optional[MockStep] = None,
        delta: Optional[MockDelta] = None,
    ):
        self.event_type = event_type
        self.interaction = interaction
        self.step = step
        self.delta = delta

    def model_dump(self, **_: Any) -> Dict[str, Any]:
        """Rend l'événement en dictionnaire, comme les événements du vrai SDK."""
        return _en_dictionnaire(self)


def fabriquer_flux_texte(
    texte: str = "Bonjour ! Voici la réponse de GoodVibe.",
    tokens_in: int = 80,
    tokens_out: int = 35,
    tokens_thought: int = 10,
    inclure_reflexion: bool = False,
) -> List[MockEvent]:
    """Fabrique une liste d'événements simulant une réponse texte complète."""
    events = [
        MockEvent(event_type="interaction.started", interaction=MockInteraction("inter_start", None)),
    ]
    if inclure_reflexion:
        events.append(
            MockEvent(
                delta=MockDelta(
                    delta_type="thought_summary",
                    content=MockDeltaContent("Analyse de la demande utilisateur et préparation d'un ton chaleureux."),
                )
            )
        )
    events.extend([
        MockEvent(delta=MockDelta(delta_type="text", text=texte)),
        MockEvent(
            event_type="interaction.completed",
            interaction=MockInteraction("inter_end", MockUsage(tokens_in, tokens_out, tokens_thought)),
        ),
    ])
    return events


def fabriquer_flux_outil(
    nom_outil: str,
    arguments: Dict[str, Any],
    reponse_finale: str = "Voici la réponse après appel d'outil.",
) -> Tuple[List[MockEvent], List[MockEvent]]:
    """Fabrique deux tours d'événements simulant l'appel d'un outil puis la réponse finale."""
    call_step = MockStep(step_type="function_call", step_id="call_mock_1", name=nom_outil)

    # Tour 1 : Demande d'outil
    tour1 = [
        MockEvent(step=call_step),
        MockEvent(delta=MockDelta(delta_type="arguments_delta", arguments=json.dumps(arguments))),
        MockEvent(event_type="step.stop"),
        MockEvent(
            event_type="interaction.completed",
            interaction=MockInteraction("inter_tour1", MockUsage(50, 20, 0)),
        ),
    ]

    # Tour 2 : Synthèse finale par l'agent
    tour2 = [
        MockEvent(delta=MockDelta(delta_type="text", text=reponse_finale)),
        MockEvent(
            event_type="interaction.completed",
            interaction=MockInteraction("inter_tour2", MockUsage(60, 30, 0)),
        ),
    ]
    return tour1, tour2


class MockInteractionsService:
    """Service interactions mocké pour le client Google GenAI."""
    def __init__(self, scenarios: Optional[List[List[MockEvent]]] = None):
        self.scenarios = list(scenarios) if scenarios else []
        self.appels: List[Dict[str, Any]] = []

    def create(self, **kwargs) -> Any:
        self.appels.append(kwargs)
        if self.scenarios:
            return self.scenarios.pop(0)
        # Réponse par défaut sécurisée
        return fabriquer_flux_texte("Réponse par défaut du modèle simulé.")


class MockGenAIClient:
    """Client simulé de l'API Google GenAI."""
    def __init__(self, scenarios: Optional[List[List[MockEvent]]] = None):
        self.interactions = MockInteractionsService(scenarios)


@pytest.fixture
def faux_gemini(monkeypatch):
    """Fixture injectant un faux client Gemini avec scénarios configurables."""
    scenarios_defaut: List[List[MockEvent]] = []
    client = MockGenAIClient(scenarios_defaut)

    # Mock des fonctions d'instanciation du client dans les modules
    import agent
    import image

    monkeypatch.setattr(agent, "get_client", lambda: client)
    monkeypatch.setattr(image, "get_client", lambda: client)

    return client
