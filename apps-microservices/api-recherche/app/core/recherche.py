from functools import lru_cache
import time
import logging
import asyncio
from typing import List, Any, Optional, Tuple, Dict
from unittest import result
from google.protobuf.json_format import MessageToDict
from openai import OpenAI
from pymilvus import DataType

from common_utils.grpc_clients import (
    embedding_client,
    database_client,
    reranking_client,
)
from app.schemas.search import (
    LLMPipeline,
    SearchRequest,
)
from app.core.credentials import settings, model_settings
from app.core.batch_processing import BatchProcessor

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class BatchingManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BatchingManager, cls).__new__(cls)
            cls._instance.embedding_batch_processor = BatchProcessor(
                cls._instance._get_embeddings_batch, 
                batch_size=settings.EMBEDDING_BATCH_SIZE, 
                max_latency=settings.EMBEDDING_MAX_LATENCY
            )
            cls._instance.reranking_batch_processor = BatchProcessor(
                cls._instance._rerank_results_batch,
                batch_size=settings.RERANKING_BATCH_SIZE,
                max_latency=settings.RERANKING_MAX_LATENCY
            )
        return cls._instance

    async def _get_embeddings_batch(self, prompts: List[str]) -> List[Optional[list]]:
        try:
            return await asyncio.gather(*[embedding_client.get_embedding(prompt) for prompt in prompts])
        except Exception as e:
            logger.error(f"Error getting embeddings for batch: {e}", exc_info=True)
            return [None] * len(prompts)

    async def _rerank_results_batch(self, rerank_requests: List[Tuple[str, List[str]]]) -> List[list]:
        try:
            return await asyncio.gather(*[reranking_client.rerank_documents_with_scores(prompt, docs) for prompt, docs in rerank_requests])
        except Exception as e:
            logger.error(f"Error reranking results for batch: {e}", exc_info=True)
            return [[] for _ in rerank_requests]

batching_manager = BatchingManager()



class LLMClientFactory:
    """Factory for creating LLM clients."""

    @staticmethod
    @lru_cache(maxsize=None)
    def get_openai_client(api_key: str) -> OpenAI:
        logger.info("Initializing OpenAI client...")
        return OpenAI(api_key=api_key)

    @staticmethod
    def get_client(model_name: str, temperature: float) -> Any:
        """
        Returns the appropriate LLM client based on the model name.
        """
        model_type = next(
            (
                key
                for key, values in model_settings.items()
                if model_name in values
            ),
            "openai",
        )

        if model_type == "openai":
            if model_name == "deepseek":
                deepseek = DeepSeek(config={"api_key": settings.DEEPSEEK_API_KEY})
                deepseek.set_temperature(temperature)
                return deepseek
            else:
                return LLMClientFactory.get_openai_client(settings.OPENAI_API_KEY)
        else:  # OpenRouter
            return OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.OPENROUTER_API_KEY,
            )


class DeepSeek:
    def __init__(self, config=None):
        config = config or {}
        self.API_KEY = config.get("api_key", settings.DEEPSEEK_API_KEY)
        self.BASE_URL = "https://api.deepseek.com"
        self.MODEL = "deepseek-chat"
        self.TEMPERATURE = 0.4
        self.client = OpenAI(api_key=self.API_KEY, base_url=self.BASE_URL)

    def chat(self, message, stream=False):
        response = self.client.chat.completions.create(
            model=self.MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Tu es un assistant intelligent et serviable.",
                },
                {"role": "user", "content": message},
            ],
            temperature=self.TEMPERATURE,
            stream=stream,
        )
        if stream:
            return response
        return {"content": response.choices[0].message.content, "response": response}

    def set_temperature(self, temperature):
        self.TEMPERATURE = float(temperature)


class FilterBuilder:
    """Builds filter expressions for database queries."""

    NUMERIC_DTYPES = {
        DataType.INT8.value,
        DataType.INT16.value,
        DataType.INT32.value,
        DataType.INT64.value,
        DataType.FLOAT.value,
        DataType.DOUBLE.value,
    }

    async def build(self, filtre: dict, source: str = "") -> list:
        clauses = []
        field_types = await database_client.get_collection_schema(source)
        if not field_types:
            logger.warning(
                f"Could not retrieve schema for collection '{source}'. Filtering will be ignored for this source."
            )
            return []

        for key, val in filtre.items():
            dtype = field_types.get(key)
            if isinstance(dtype, DataType):
                dtype = dtype.value
            else:
                dtype = dtype

            if key == "id_categorie" and source == "produits":
                key = "categorie"
            elif key == "id_categorie" and source == "siteweb":
                continue

            if not dtype:
                continue

            if dtype == DataType.ARRAY:
                clauses.append(self._build_array_clause(key, val))
            elif dtype in self.NUMERIC_DTYPES:
                clauses.append(self._build_numeric_clause(key, val, dtype))
            else:
                clauses.append(self._build_string_clause(key, val, source))

        return [c for c in clauses if c]

    def _build_array_clause(self, key: str, val: Any) -> str:
        if isinstance(val, list):
            sub_clauses = [f"array_contains({key}, {repr(str(v))})" for v in val]
            return f"({' or '.join(sub_clauses)})" if sub_clauses else ""
        else:
            return f"array_contains({key}, {repr(str(val))})"

    def _build_numeric_clause(self, key: str, val: Any, dtype: int) -> str:
        if isinstance(val, dict) and "operator" in val and "values" in val:
            return self._build_operator_clause(key, val)
        elif isinstance(val, list):
            numeric_vals = [
                self._cast_numeric(v, dtype) for v in val
            ]
            return f"{key} in {numeric_vals}"
        else:
            numeric_val = self._cast_numeric(val, dtype)
            return f"{key} == {numeric_val}"

    def _build_string_clause(self, key: str, val: Any, source: str) -> str:
        if isinstance(val, dict) and "operator" in val and "values" in val:
            return self._build_operator_clause(key, val)
        elif isinstance(val, list):
            if key == "id_categorie" and source == "devis":
                numeric_vals = [int(v) for v in val]
                return f"{key} in {numeric_vals}"
            quoted_vals = [repr(str(v)) for v in val]
            return f"{key} in [{', '.join(quoted_vals)}]"
        else:
            return f"{key} == {repr(str(val))}"

    def _build_operator_clause(self, key: str, val: dict) -> str:
        operator = val["operator"]
        values = val["values"]
        if (
            operator == "entre"
            and isinstance(values, dict)
            and "start" in values
            and "end" in values
        ):
            return f"{key} >= {values['start']} and {key} <= {values['end']}"
        else:
            actual_value = next(iter(values.values()))
            return f"{key} {operator} {actual_value}"

    def _cast_numeric(self, value: Any, dtype: int) -> Any:
        if dtype in {DataType.INT8, DataType.INT16, DataType.INT32, DataType.INT64}:
            return int(value)
        else:
            return float(value)


class ContextBuilder:
    """Builds context from search results."""

    def build(self, matches: List[Dict[str, str]]) -> list:
        context_texts = []
        for res in matches:
            source = res.get("source", "N/A")
            metadata = res.get("metadata", {}).get("entity", {})
            
            title_extractors = {
                "produits_3": lambda m: m.get("nom_produit", "N/A"),
                "siteweb_2": lambda m: m.get("url", "N/A"),
                "devis": lambda m: m.get("lead_id", "N/A"),
                "echanges": lambda m: m.get("conversation_id", "N/A"),
            }
            
            fournisseur_extractors = {
                "produits_3": lambda m: m.get("fournisseur", "N/A"),
                "siteweb_2": lambda m: m.get("fournisseur", "N/A"),
                "echanges": lambda m: m.get("fournisseur", "N/A"),
            }

            title = title_extractors.get(source, lambda m: "N/A")(metadata)
            fournisseur = fournisseur_extractors.get(source, lambda m: "N/A")(metadata)
            categorie = metadata.get("categorie", "N/A")
            text = metadata.get("text", "")

            source_map = {
                "produits_3": "Produits",
                "siteweb_2": "Siteweb",
            }
            source_display = source_map.get(source, source)

            context_texts.append(
                f"""Titre : {title}
                    Source : {source_display}
                    Fournisseur : {fournisseur}
                    Catégorie : {categorie}
                    Texte : {text}
                """
            )
        return context_texts


class SearchOrchestrator:
    """Orchestrates the search process."""

    def __init__(self, request: SearchRequest):
        self.request = request
        self.filter_builder = FilterBuilder()
        self.context_builder = ContextBuilder()

    async def search_stream(self):
        """Orchestrates the streaming search flow."""
        start_total_time = time.perf_counter()
        try:
            yield {"type": "status", "payload": "Starting search stream..."}

            query_vector, embed_duration = await self._get_embedding()
            yield {"type": "embedding_complete", "payload": {"duration": round(embed_duration, 2)}}

            initial_matches_dict, search_duration = await self._perform_search(query_vector)
            initial_matches = []
            for matches in initial_matches_dict.values():
                initial_matches.extend(matches)
            initial_matches = sorted(initial_matches, key=lambda x: x.get("score", 0.0), reverse=True)
            yield {"type": "initial_results", "payload": {"results": initial_matches, "duration": round(search_duration, 2)}}

            final_results, rerank_duration = await self._rerank_results(initial_matches)
            if rerank_duration > 0:
                yield {"type": "rerank_complete", "payload": {"results": final_results, "duration": round(rerank_duration, 2)}}

            llm_duration = 0
            if self.request.action == 2 and final_results:
                start_llm_time = time.perf_counter()
                context_texts = self.context_builder.build(final_results)
                llm_pipeline = await self._run_llm_pipeline(context_texts)
                
                yield {
                    "type": "llm_chunk" if not llm_pipeline.error else "error",
                    "payload": llm_pipeline.llm_response,
                    "llm_response": llm_pipeline.response,
                }
                llm_duration = time.perf_counter() - start_llm_time

            total_duration = time.perf_counter() - start_total_time
            final_summary = {
                "timings": {
                    "embedding": round(embed_duration, 2),
                    "vector_search": round(search_duration, 2),
                    "rerank": round(rerank_duration, 2),
                    "llm_execution": round(llm_duration, 2),
                    "total_process": round(total_duration, 2),
                },
                "result_count": len(final_results),
            }
            yield {"type": "end_of_stream", "payload": final_summary}

        except Exception as e:
            logger.error(f"A major error occurred in the search stream: {e}", exc_info=True)
            yield {"type": "error", "payload": f"Server error: {e}"}
        finally:
            logger.info("Search stream finished.")

    async def search(self) -> dict:
        """Orchestrates a complete non-streaming search."""
        start_total_time = time.perf_counter()
        embed_duration, search_duration, rerank_duration, llm_duration = 0, 0, 0, 0
        llm_req = LLMPipeline(llm_response="", context="", full_user_prompt="", response={}, llm_duration=0)
        final_filter_expr_str = ""
        all_results = {}

        try:
            query_vector, embed_duration = await self._get_embedding()
            
            all_results, search_duration = await self._perform_search(query_vector)

            if self.request.options.use_reranker and all_results:
                start_rerank_time = time.perf_counter()
                reranked_results_by_source = {}
                for source, matches in all_results.items():
                    if not matches:
                        reranked_results_by_source[source] = []
                        continue
                    docs_to_rerank = [match["metadata"]["entity"]["text"] for match in matches]
                    ranked_texts = await batching_manager.reranking_batch_processor.process((self.request.prompt, docs_to_rerank))
                    result_map = {res["metadata"]["entity"]["text"]: res for res in matches}
                    res_by_source = []
                    for item in ranked_texts:
                        score = float(item.get("score", 0.0))
                        document = item.get("document", "")
                        if document not in result_map:
                            continue
                        
                        result_map[document]["reranking"] = score
                        
                        if 'text' not in self.request.fields and self.request.fields != []:
                            result_map[document].get('metadata', {}).get('entity', {}).pop('text', None)
                            
                        res_by_source.append(result_map[document])
                    reranked_results_by_source[source] = res_by_source[:int(self.request.top_k)]
                        

                all_results = reranked_results_by_source
                rerank_duration = time.perf_counter() - start_rerank_time
            else:
                for source, matches in all_results.items():
                    sorted_matches = sorted(matches, key=lambda x: x.get("score", 0.0), reverse=True)
                    all_results[source] = sorted_matches[:top_k_final]

            context_texts = []
            for matches in all_results.values():
                context_texts.extend(self.context_builder.build(matches))
            
            llm_req = await self._run_llm_pipeline(context_texts)

        except Exception as e:
            logger.error(f"A major error occurred in the non-streaming search: {e}", exc_info=True)
            return self._build_error_response(str(e), embed_duration, search_duration, rerank_duration, llm_duration, start_total_time, llm_req)

        total_duration = time.perf_counter() - start_total_time
        return {
            "database": "milvus",
            "user_query": self.request.prompt,
            "filter": final_filter_expr_str,
            "matches": all_results,
            "context": llm_req.context,
            "response": llm_req.llm_response,
            "embedding": round(embed_duration, 2),
            "fournisseur_non_vide": None,
            "full_user_prompt": llm_req.full_user_prompt,
            "chat_model": self.request.llm.chat_model,
            "temperature": self.request.llm.temperature,
            "vector_search": round(search_duration, 2),
            "rerank_duration": round(rerank_duration, 2),
            "llm_execution": round(llm_req.llm_duration, 2),
            "total_process": round(total_duration, 2),
            "import_duration": 0,
            "llm_reponse": llm_req.response,
        }

    async def search_classique_stream(self):
        start_total_time = time.perf_counter()
        try:
            yield {"type": "status", "payload": "Starting classic search stream..."}

            final_results, search_duration = await self._perform_classic_search()
            yield {"type": "initial_results", "payload": {"results": final_results, "duration": round(search_duration, 2)}}

            llm_duration = 0
            if self.request.action == 2 and final_results:
                start_llm_time = time.perf_counter()
                context_texts = self.context_builder.build(final_results)
                llm_pipeline = await self._run_llm_pipeline(context_texts)
                
                yield {
                    "type": "llm_chunk" if not llm_pipeline.error else "error",
                    "payload": llm_pipeline.llm_response,
                    "llm_response": llm_pipeline.response,
                }
                llm_duration = time.perf_counter() - start_llm_time

            total_duration = time.perf_counter() - start_total_time
            final_summary = {
                "timings": {
                    "embedding": 0,
                    "vector_search": round(search_duration, 2),
                    "rerank": 0,
                    "llm_execution": round(llm_duration, 2),
                    "total_process": round(total_duration, 2),
                },
                "result_count": len(final_results),
            }
            yield {"type": "end_of_stream", "payload": final_summary}

        except Exception as e:
            logger.error(f"A major error occurred in the classic search stream: {e}", exc_info=True)
            yield {"type": "error", "payload": f"Server error: {e}"}
        finally:
            logger.info("Classic search stream finished.")

    async def search_classique(self) -> dict:
        start_total_time = time.perf_counter()
        search_duration, llm_duration = 0, 0
        llm_req = LLMPipeline(llm_response="", context="", full_user_prompt="", response={}, llm_duration=0)
        final_filter_expr_str = ""
        all_results = {}

        try:
            start_search = time.perf_counter()
            top_k_final = int(self.request.top_k)

            for item in self.request.source:
                source_name = item.source
                filtre = item.filtre
                
                final_filter_expr = await self._build_filter_expression(filtre, source_name)
                final_filter_expr_str = final_filter_expr

                source_results = await database_client.classic_search_vector(
                    collection=source_name, filter_expr=final_filter_expr, k=top_k_final, output_fields=self.request.fields if self.request.fields else None
                )
                all_results[source_name] = [MessageToDict(res) for res in source_results]
            
            search_duration = time.perf_counter() - start_search

            context_texts = []
            for matches in all_results.values():
                context_texts.extend(self.context_builder.build(matches))
            
            llm_req = await self._run_llm_pipeline(context_texts)

        except Exception as e:
            logger.error(f"A major error occurred in the classic non-streaming search: {e}", exc_info=True)
            return self._build_error_response(str(e), 0, search_duration, 0, llm_duration, start_total_time, llm_req)

        total_duration = time.perf_counter() - start_total_time
        return {
            "database": "milvus",
            "user_query": self.request.prompt,
            "filter": final_filter_expr_str,
            "matches": all_results,
            "context": llm_req.context,
            "response": llm_req.llm_response,
            "embedding": 0,
            "fournisseur_non_vide": None,
            "full_user_prompt": llm_req.full_user_prompt,
            "chat_model": self.request.llm.chat_model,
            "temperature": self.request.llm.temperature,
            "vector_search": round(search_duration, 2),
            "rerank_duration": 0,
            "llm_execution": round(llm_req.llm_duration, 2),
            "total_process": round(total_duration, 2),
            "import_duration": 0,
            "llm_reponse": llm_req.response,
        }

    async def _get_embedding(self) -> Tuple[Optional[list], float]:
        start_embed = time.perf_counter()
        query_vector = await batching_manager.embedding_batch_processor.process(self.request.prompt)
        embed_duration = time.perf_counter() - start_embed
        if not query_vector:
            raise ValueError("Could not generate embedding for the query.")
        return query_vector, embed_duration

    async def _perform_search(self, query_vector: list) -> Tuple[Dict[str, list], float]:
        top_k_final = int(self.request.top_k)
        top_k_retrieval = top_k_final * 2 if self.request.options.use_reranker else top_k_final
        
        start_search_time = time.perf_counter()
        search_tasks = []
        source_names = []
        for item in self.request.source:
            source_names.append(item.source)
            search_tasks.append(self._create_search_task(item.source, item.filtre, query_vector, top_k_retrieval))

        list_of_results_groups = await asyncio.gather(*search_tasks, return_exceptions=True)
        search_duration = time.perf_counter() - start_search_time

        all_results = {}
        for i, source_results in enumerate(list_of_results_groups):
            source_name = source_names[i]
            if isinstance(source_results, Exception):
                logger.error(f"A search task failed for source {source_name}: {source_results}")
                all_results[source_name] = []
                continue
            if source_results:
                all_results[source_name] = [MessageToDict(res) for res in source_results]
            else:
                all_results[source_name] = []

        return all_results, search_duration

    async def _perform_classic_search(self) -> Tuple[list, float]:
        top_k_final = int(self.request.top_k)
        start_search_time = time.perf_counter()
        all_source_results = []

        for item in self.request.source:
            source_name = item.source
            filtre = item.filtre
            
            final_filter_expr = await self._build_filter_expression(filtre, source_name)

            source_results = await database_client.classic_search_vector(
                collection=source_name, filter_expr=final_filter_expr, k=top_k_final
            )

            if source_results:
                all_source_results.extend([MessageToDict(res) for res in source_results])

        search_duration = time.perf_counter() - start_search_time
        return all_source_results, search_duration

    async def _create_search_task(self, source_name, filtre, query_vector, k):
        final_filter_expr = await self._build_filter_expression(filtre, source_name)
        return await database_client.search_vector(
            collection=source_name,
            vector=query_vector,
            k=k,
            filter_expr=final_filter_expr,
        )

    async def _build_filter_expression(self, filtre: dict, source_name: str) -> str:
        filters = []
        filter_expr_global = await self.filter_builder.build(self.request.filtre, source_name)
        if filter_expr_global:
            filters.append(" and ".join(filter_expr_global))

        filter_expr_source = await self.filter_builder.build(filtre, source_name) if filtre else ""
        if filter_expr_source:
            filters.append(" and ".join(filter_expr_source))
        
        return " and ".join(filters) if filters else ""

    async def _rerank_results(self, initial_matches: list) -> Tuple[list, float]:
        if not self.request.options.use_reranker or not initial_matches:
            return initial_matches, 0

        start_rerank_time = time.perf_counter()
        docs_to_rerank = []
        result_map = {}
        for res in initial_matches:
            doc_text = res.get("metadata", {}).get("entity", {}).get("text")
            if doc_text and doc_text not in result_map:
                docs_to_rerank.append(doc_text)
                result_map[doc_text] = res
        
        if not docs_to_rerank:
            return initial_matches, 0

        ranked_texts = await reranking_client.rerank_documents_with_scores(self.request.prompt, docs_to_rerank)
        # final_results = [result_map[text] for text in ranked_texts if text in result_map]
        final_results = []
        for item in ranked_texts:
            score = float(item.get("score", 0.0))
            if item.get("document", "") not in result_map:
                continue
            
            result_map[item.get("document")]["reranking"] = score
            final_results.append(result_map[item.get("document")])

        rerank_duration = time.perf_counter() - start_rerank_time
        
        return final_results, rerank_duration

    async def _run_llm_pipeline(self, context_texts: list) -> LLMPipeline:
        if not context_texts or self.request.action != 2:
            return LLMPipeline(llm_response="", context="", full_user_prompt="", response={}, llm_duration=0)

        context ="""
            -----


            """.join(context_texts)
        try:
            full_user_prompt = self.request.llm.template_prompt.format(
                chunks=context, recherche=self.request.prompt
            )
        except (KeyError, ValueError) as e:
            error_message = f"Prompt formatting error: key '{e}' is missing or format is invalid."
            logger.error(error_message)
            return LLMPipeline(llm_response=error_message, context=context, error=True)

        client = LLMClientFactory.get_client(self.request.llm.chat_model, self.request.llm.temperature)
        
        start_llm_time = time.perf_counter()
        llm_response, completion = "", {}

        try:
            if isinstance(client, DeepSeek):
                response = client.chat(full_user_prompt)
                llm_response = response["content"]
                completion = response["response"]
            else:
                completion = client.chat.completions.create(
                    model=self.request.llm.chat_model,
                    messages=[{"role": "user", "content": full_user_prompt}],
                    temperature=float(self.request.llm.temperature),
                )
                llm_response = completion.choices[0].message.content
            
            completion = completion.model_dump()
        except Exception as e:
            logger.error(f"Error during LLM execution: {e}")
            return LLMPipeline(llm_response=str(e), context=context, full_user_prompt=full_user_prompt, error=True, llm_duration=0)

        llm_duration = time.perf_counter() - start_llm_time
        return LLMPipeline(
            llm_duration=float(llm_duration),
            llm_response=llm_response,
            full_user_prompt=full_user_prompt,
            context=context,
            response=completion,
        )
    
    def _build_error_response(self, error_message, embed_duration, search_duration, rerank_duration, llm_duration, start_total_time, llm_req):
        return {
            "database": "milvus",
            "user_query": self.request.prompt,
            "filter": "",
            "matches": {},
            "context": "",
            "response": f"Server error: {error_message}",
            "embedding": round(embed_duration, 2),
            "fournisseur_non_vide": None,
            "full_user_prompt": "",
            "chat_model": self.request.llm.chat_model,
            "temperature": self.request.llm.temperature,
            "vector_search": round(search_duration, 2),
            "rerank_duration": round(rerank_duration, 2),
            "llm_execution": round(llm_duration, 2),
            "total_process": round(time.perf_counter() - start_total_time, 2),
            "import_duration": 0,
            "llm_reponse": llm_req.response,
        }


async def search_in_milvus_stream(request: SearchRequest):
    orchestrator = SearchOrchestrator(request)
    async for item in orchestrator.search_stream():
        yield item


async def search_in_milvus(request: SearchRequest) -> dict:
    orchestrator = SearchOrchestrator(request)
    return await orchestrator.search()


async def search_in_milvus_classique_stream(request: SearchRequest):
    orchestrator = SearchOrchestrator(request)
    async for item in orchestrator.search_classique_stream():
        yield item


async def search_in_milvus_classique(request: SearchRequest) -> dict:
    orchestrator = SearchOrchestrator(request)
    return await orchestrator.search_classique()
