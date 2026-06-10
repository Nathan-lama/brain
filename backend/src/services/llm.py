import os
from typing import Literal

import instructor
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from src.models import NodeType

# Configuration variables
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()
CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen2.5:7b-instruct")
LLM_MODEL = os.getenv("LLM_MODEL", CHAT_MODEL)
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")

if LLM_PROVIDER == "ollama":
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
else:
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")


class ExtractedClaim(BaseModel):
    raisonnement: str = Field(
        ...,
        description="Raisonnement et justification quant au contenu, au type et au domaine du claim.",
    )
    temp_id: str = Field(
        ...,
        description="Un identifiant temporaire unique pour ce claim (ex: claim_1, claim_2).",
    )
    type: NodeType = Field(
        ...,
        description="Le type du claim: descriptif, empirique, normatif_position, normatif_conclusion, definitionnel.",
    )
    domain: str = Field(
        ...,
        description="Le domaine thématique principal du claim (ex: climat, ethique, metaphysique, politique, economie).",
    )
    text: str = Field(
        ..., description="Le texte exact ou reformulé de l'assertion extraite."
    )
    tier: Literal["certain", "fort", "moyen", "faible", "speculatif"] = Field(
        ...,
        description="Le palier de crédence/certitude ou d'engagement de l'assertion (certain, fort, moyen, faible, speculatif).",
    )


class ClaimsExtractionResponse(BaseModel):
    raisonnement: str = Field(
        ...,
        description="Raisonnement global sur la décomposition du texte en claims indépendants.",
    )
    claims: list[ExtractedClaim] = Field(
        ..., description="Liste des claims extraits du texte."
    )


class RelationItem(BaseModel):
    raisonnement: str = Field(
        ...,
        description="Raisonnement expliquant pourquoi ces deux claims ont cette relation ou s'ils sont indépendants.",
    )
    relation_type: Literal[
        "soutient", "contredit", "implique", "presuppose", "independant"
    ] = Field(
        ...,
        description="Le type de relation logique ou d'opposition. Utilisez 'independant' s'il n'y a pas de lien direct.",
    )
    source_id: str = Field(..., description="ID temporaire du claim source (nouveau).")
    target_id: str = Field(
        ...,
        description="ID du claim cible (qui peut être un nouveau claim ou l'UUID d'un claim existant de la base de données).",
    )
    bridge_text: str | None = Field(
        None,
        description="Si la relation est 'soutient' ou 'implique' et qu'il y a un saut logique descriptif -> normatif, formulez ici une prémisse de type 'pont_normatif' sous forme de condition normative (ex: 'Si [fait], alors nous devons [action]'). Laissez à null sinon.",
    )
    bridge_domain: str | None = Field(
        None,
        description="Le domaine du pont normatif généré (ex: 'ethique', 'politique'). Laissez à null sinon.",
    )


class RelationExtractionResponse(BaseModel):
    raisonnement: str = Field(
        ...,
        description="Raisonnement général sur les relations logiques et de conflit à établir.",
    )
    relations: list[RelationItem] = Field(
        ..., description="Liste des relations identifiées entre les claims."
    )


class LLMClient:
    def __init__(
        self,
        provider: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ):
        self.provider = provider or os.getenv("LLM_PROVIDER", "ollama").lower()

        default_base_url = (
            "http://localhost:11434/v1"
            if self.provider == "ollama"
            else "https://api.openai.com/v1"
        )
        self.base_url = base_url or os.getenv("LLM_BASE_URL") or default_base_url
        self.model = (
            model
            or os.getenv("LLM_MODEL")
            or os.getenv("CHAT_MODEL", "qwen2.5:7b-instruct")
        )
        self.api_key = (
            api_key
            or os.getenv("LLM_API_KEY")
            or ("ollama" if self.provider == "ollama" else "")
        )

        # Configure the instructor client wrapping the AsyncOpenAI client
        self.raw_client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key if self.api_key else "ollama",
            timeout=5.0,
        )
        self.client = instructor.from_openai(self.raw_client, mode=instructor.Mode.JSON)

    async def extract_claims(self, text: str) -> ClaimsExtractionResponse:
        prompt = (
            f"Analysez le texte suivant et décomposez-le en claims (croyances) logiquement indépendants.\n"
            f"Chaque claim doit correspondre à une affirmation claire et autonome.\n"
            f"Déterminez son type, son domaine principal, son texte et son niveau de confiance.\n\n"
            f'Texte à analyser :\n"""\n{text}\n"""'
        )

        return await self.client.chat.completions.create(
            model=self.model,
            response_model=ClaimsExtractionResponse,
            messages=[
                {
                    "role": "system",
                    "content": "Vous êtes un expert en analyse argumentative et logique formelle.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )

    async def extract_relations(
        self, new_claims: list[dict], existing_claims: list[dict]
    ) -> RelationExtractionResponse:
        new_claims_str = "\n".join(
            [
                f'- ID temporaire: {c["temp_id"]} | Type: {c["type"]} | Domaine: {c["domain"]} | Texte: "{c["text"]}"'
                for c in new_claims
            ]
        )

        existing_claims_str = (
            "\n".join(
                [
                    f'- ID existant (UUID): {c["id"]} | Type: {c["type"]} | Domaine: {c["domain"]} | Texte: "{c["text"]}"'
                    for c in existing_claims
                ]
            )
            if existing_claims
            else "Aucun claim existant dans la base de données."
        )

        prompt = (
            f"Analysez les relations logiques et de contradiction entre les nouveaux claims et, si applicables, les claims existants de la base de données.\n\n"
            f"Nouveaux claims extraits :\n{new_claims_str}\n\n"
            f"Claims existants proches :\n{existing_claims_str}\n\n"
            f"Directives :\n"
            f"1. Déterminez pour chaque paire pertinente si une relation existe : 'soutient', 'contredit', 'implique', ou 'presuppose'. Sinon, utilisez 'independant'.\n"
            f"2. IDENTIFIEZ LES SAUTS DESCRIPTIFS -> NORMATIFS : Si une prémisse descriptive (type 'descriptif' ou 'empirique') sert à justifier ou soutenir une conclusion ou une position normative (type 'normatif_position' ou 'normatif_conclusion'), vous DEVEZ générer une prémisse-pont ('pont_normatif') et l'indiquer dans le champ 'bridge_text'. Par exemple, si le fait est 'La méritocratie suppose la liberté' et la conclusion est 'Nous devons défendre la méritocratie', alors le pont normatif peut être 'Le mérite requiert une origination ultime (libre arbitre)'.\n"
            f"3. La prémisse-pont ('pont_normatif') doit être formulée comme une règle générale reliant le fait à la valeur (ex: 'Si A est vrai, alors B doit être fait')."
        )

        return await self.client.chat.completions.create(
            model=self.model,
            response_model=RelationExtractionResponse,
            messages=[
                {
                    "role": "system",
                    "content": "Vous êtes un expert en analyse argumentative et cartographie d'arguments (AIF).",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )

    async def generate_synthesis_note(self, data_context: str) -> str:
        prompt = (
            f"En tant qu'assistant de recherche philosophique et politique, rédigez une note de synthèse "
            f"structurée et élégante en Markdown basée sur l'analyse de cohérence et de causalité suivante.\n"
            f"La note doit détailler la thèse ou le domaine concerné, présenter la position cohérente majeure, "
            f"analyser les tensions logiques ou paradoxes existants, et explorer les visions rivales alternatives.\n"
            f"Faites des paragraphes rédigés et clairs, adaptés pour nourrir un essai ou une vidéo.\n\n"
            f"Données de l'analyse :\n{data_context}"
        )
        try:
            res = await self.raw_client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Vous êtes un rédacteur d'essais philosophiques et un analyste logique.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
            )
            return res.choices[0].message.content
        except Exception as e:
            # Fallback to returning raw data formatted nicely
            return f"# Note de Synthèse (Génération Directe)\n\nUne erreur est survenue lors de l'appel au LLM ({str(e)}). Voici les données brutes de l'analyse :\n\n{data_context}"
