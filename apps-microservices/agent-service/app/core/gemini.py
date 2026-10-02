"""Gemini d'agent-service : ChatGoogleGenerativeAI, avec la recherche Google et la lecture de pages via Interactions.

generateContent, seule API de langchain-google-genai 4.4.0, ne lançait aucune recherche avec gemini-3.1-flash-lite
(testé le 01/10/2026 ; cas proche : google-gemini/cookbook#1274). Les appels sans ces outils restent ceux de
ChatGoogleGenerativeAI. Limites d'Interactions ici : un seul tour, pas de température (champ absent de l'API).
"""
from typing import Any, AsyncIterator, Iterator, List, Optional

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_google_genai import ChatGoogleGenerativeAI

OUTILS_INTERACTIONS = ("google_search", "url_context")


class ErreurGeminiInteractions(Exception):
    pass


class ChatGemini(ChatGoogleGenerativeAI):

    @property
    def _llm_type(self) -> str:
        return "chat-gemini-hellopro"

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
                  run_manager: Any = None, **kwargs: Any) -> ChatResult:
        outils = self._outils_interactions(kwargs.get("tools"))
        if not outils:
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

        interactions = self._sans_relance(self.client.interactions)
        interaction = interactions.create(**self._requete(messages, outils))
        return ChatResult(generations=[ChatGeneration(message=self._message(interaction))])

    async def _agenerate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
                         run_manager: Any = None, **kwargs: Any) -> ChatResult:
        outils = self._outils_interactions(kwargs.get("tools"))
        if not outils:
            return await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)

        interactions = self._sans_relance(self.client.aio.interactions)
        interaction = await interactions.create(**self._requete(messages, outils))
        return ChatResult(generations=[ChatGeneration(message=self._message(interaction))])

    # Avec recherche ou lecture, la réponse arrive en un seul morceau (sinon : streaming de ChatGoogleGenerativeAI)
    def _stream(self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
                run_manager: Any = None, **kwargs: Any) -> Iterator[ChatGenerationChunk]:
        if not self._outils_interactions(kwargs.get("tools")):
            yield from super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)
            return
        resultat = self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        yield self._morceau(resultat.generations[0].message)

    async def _astream(self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
                       run_manager: Any = None, **kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        if not self._outils_interactions(kwargs.get("tools")):
            async for morceau in super()._astream(messages, stop=stop, run_manager=run_manager, **kwargs):
                yield morceau
            return
        resultat = await self._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
        yield self._morceau(resultat.generations[0].message)

    def _outils_interactions(self, outils: Optional[list]) -> List[str]:
        """Outils de la liste à passer par Interactions ; [] si aucun (appel generateContent normal)."""
        noms, autres = [], []
        for outil in outils or []:
            donnees = outil.model_dump() if hasattr(outil, "model_dump") else dict(outil)
            for cle, valeur in donnees.items():
                if valeur is None:
                    continue
                if cle in OUTILS_INTERACTIONS:
                    noms.append(cle)
                else:
                    autres.append(cle)

        if noms and autres:
            raise ErreurGeminiInteractions(f"outils non gérés avec la recherche ou la lecture de pages : {autres}")
        return noms

    def _sans_relance(self, ressource):
        # Le client Interactions du SDK relance seul (1 fois au minimum, même avec HttpRetryOptions) :
        # on applique max_retries de LangChain, 0 dans agent-service (budget de 300 s du curl PHP).
        ressource.sdk_configuration.retry_config.max_retries = self.max_retries
        return ressource

    def _requete(self, messages: List[BaseMessage], outils: List[str]) -> dict:
        instructions = "\n\n".join(m.text for m in messages if isinstance(m, SystemMessage))
        entrees = [m for m in messages if isinstance(m, HumanMessage)]
        if len(entrees) != 1 or any(isinstance(m, AIMessage) for m in messages):
            raise ErreurGeminiInteractions(
                "conversation à plusieurs tours non gérée avec la recherche (relance désactivée)")

        requete = {
            "model": self.model,
            "input": entrees[0].text,
            "tools": [{"type": nom} for nom in outils],
            "store": False,  # pas de conservation de l'échange côté Google
            "timeout": self.timeout,
        }
        if instructions:
            requete["system_instruction"] = instructions
        if self.max_output_tokens:
            requete["generation_config"] = {"max_output_tokens": self.max_output_tokens}
        return requete

    def _message(self, interaction: Any) -> AIMessage:
        donnees = interaction.model_dump(mode="json", exclude_none=True)
        if donnees.get("status") != "completed":
            raise ErreurGeminiInteractions(f"interaction en statut {donnees.get('status')}")

        requetes, urls, sources = [], [], []
        for etape in donnees.get("steps") or []:
            arguments = etape.get("arguments") or {}
            if etape.get("type") == "google_search_call":
                requetes.extend(arguments.get("queries") or [])
            if etape.get("type") == "url_context_call":
                urls.extend(arguments.get("urls") or [])
            if etape.get("type") == "model_output":
                for bloc in etape.get("content") or []:
                    for note in bloc.get("annotations") or []:
                        source = {"url": note.get("url"), "title": note.get("title")}
                        if note.get("type") == "url_citation" and source not in sources:
                            sources.append(source)

        usage = donnees.get("usage") or {}
        tokens_entree = int(usage.get("total_input_tokens") or 0)
        # Réflexion facturée au tarif sortie (valait 0 sur les tests du 01/10/2026)
        tokens_sortie = int(usage.get("total_output_tokens") or 0) + int(usage.get("total_thought_tokens") or 0)
        # Chiffre facturé : search_query_count, que le SDK 2.25 ne garde pas ; count lui était égal
        # dans les réponses réelles du 01/10/2026 (1/1 et 10/10). Pas le nombre de requêtes des étapes.
        nb_recherches = sum(int(outil.get("search_query_count", outil.get("count")) or 0)
                            for outil in usage.get("grounding_tool_count") or []
                            if outil.get("type") == "google_search")

        return AIMessage(
            content=interaction.output_text or "",
            usage_metadata={"input_tokens": tokens_entree, "output_tokens": tokens_sortie,
                            "total_tokens": tokens_entree + tokens_sortie,
                            "input_token_details": {"cache_read": int(usage.get("total_cached_tokens") or 0)}},
            response_metadata={"model_name": donnees.get("model", self.model), "model_provider": "google_genai",
                               "api": "interactions", "interaction_id": donnees.get("id"),
                               "status": donnees.get("status"), "nb_recherches": nb_recherches,
                               "requetes_recherche": requetes, "urls_lues": urls, "sources": sources},
        )

    @staticmethod
    def _morceau(message: AIMessage) -> ChatGenerationChunk:
        return ChatGenerationChunk(message=AIMessageChunk(content=message.content,
                                                          usage_metadata=message.usage_metadata,
                                                          response_metadata=message.response_metadata))
