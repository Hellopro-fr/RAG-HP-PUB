import logging
import json
import asyncio
import re
from typing import List, Dict, Optional, Any, TypedDict

from langgraph.graph import END, StateGraph
from langchain_core.documents import Document

from app.domain.models import QueryResponse
from app.services.cypher_builder import cypher_builder
from app.services.rag_components import ROUTER_PROMPT, ANSWER_GENERATION_TEMPLATE
from app.infrastructure.clients import clients
from app.infrastructure.llm_service import llm_service


class GraphState(TypedDict):
    question: str
    generation: str
    documents: List[Document]
    candidate_ids: List[str]
    graph_documents: List[Document]
    vector_documents: List[Document]
    cypher: str
    cypher_params: Dict[str, Any]
    routing_decision: str
    extracted_data: Dict[str, Any]


class AgenticRAGService:
    def __init__(self):
        workflow = StateGraph(GraphState)

        workflow.add_node("decide_strategy", self.decide_strategy)
        workflow.add_node("retrieve_vectorstore_only", self.retrieve)
        workflow.add_node("grade_documents", self.grade_documents)
        workflow.add_node("decide_to_generate", self.decide_to_generate)
        workflow.add_node("graph_search_only", self.graph_search)
        workflow.add_node("retrieve_vector_candidates", self.retrieve_vector_candidates)
        workflow.add_node("filter_with_graph", self.filter_with_graph)
        workflow.add_node("parallel_retrieve", self.parallel_retrieve)
        workflow.add_node("merge_and_rerank", self.merge_and_rerank)
        workflow.add_node("generate", self.generate)
        workflow.add_node("handle_no_documents", self.handle_no_documents)

        workflow.set_entry_point("decide_strategy")

        workflow.add_conditional_edges(
            "decide_strategy",
            lambda state: state["routing_decision"],
            {
                "vectorstore_only": "retrieve_vectorstore_only",
                "graph_only": "graph_search_only",
                "sequential_refinement": "retrieve_vector_candidates",
                "parallel_fusion": "parallel_retrieve",
            },
        )

        workflow.add_edge("retrieve_vectorstore_only", "grade_documents")
        workflow.add_edge("grade_documents", "decide_to_generate")
        workflow.add_edge("graph_search_only", "generate")
        workflow.add_edge("retrieve_vector_candidates", "filter_with_graph")
        workflow.add_edge("filter_with_graph", "generate")
        workflow.add_edge("parallel_retrieve", "merge_and_rerank")
        workflow.add_edge("merge_and_rerank", "grade_documents")

        workflow.add_conditional_edges(
            "decide_to_generate",
            lambda state: (
                "generate" if state.get("documents") else "handle_no_documents"
            ),
            {"generate": "generate", "handle_no_documents": "handle_no_documents"},
        )

        workflow.add_edge("handle_no_documents", END)
        workflow.add_edge("generate", END)

        self.app = workflow.compile()

    async def decide_strategy(self, state: GraphState) -> Dict:
        logging.info("--- DECIDING RETRIEVAL STRATEGY ---")
        question = state["question"]

        if state.get("routing_decision"):
            return {"routing_decision": state["routing_decision"]}

        try:
            response = await llm_service.invoke_chain(
                ROUTER_PROMPT, {"question": question}
            )
            # Clean JSON
            if "```json" in response:
                response = response[response.find("{") : response.rfind("}") + 1]
            decision_json = json.loads(response)
            decision = decision_json.get("strategy", "vectorstore_only")
        except Exception:
            decision = "vectorstore_only"

        logging.info(f"Routing decision: {decision}")
        return {"routing_decision": decision}

    async def _run_vector_retrieval(self, question: str) -> List[Document]:
        logging.info("--- HELPER: RETRIEVING FROM VECTORSTORE ---")
        embedding = await clients.get_embedding(question)
        if not embedding:
            return []

        results = await clients.search_vectors(embedding, top_k=10)
        docs = []
        for res in results:
            # We might want to fetch full details here if Milvus only returns IDs
            # For now, we assume we need to fetch details or Milvus returns metadata
            # In the new architecture, search_vectors returns id and score.
            # We should fetch node properties from Neo4j for context.
            doc = Document(
                page_content=f"Product ID: {res['id']}",
                metadata={"id": res["id"], "score": res["score"]},
            )
            docs.append(doc)
        return docs

    async def _run_graph_retrieval(
        self, question: str, candidate_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        logging.info(f"--- HELPER: RETRIEVING FROM GRAPH ---")
        cypher, _, params = await cypher_builder.extract_entities_and_build_cypher(
            question, candidate_ids
        )

        if not cypher:
            return {"documents": [], "cypher": None, "params": {}}

        context = await clients.execute_cypher(cypher, params)
        docs = []
        if context:
            for item in context:
                # Flatten result
                content = json.dumps(item, ensure_ascii=False, default=str)
                docs.append(Document(page_content=content))

        return {"documents": docs, "cypher": cypher, "params": params}

    async def retrieve(self, state: GraphState) -> Dict:
        documents = await self._run_vector_retrieval(state["question"])
        return {"documents": documents}

    async def graph_search(self, state: GraphState) -> Dict:
        result = await self._run_graph_retrieval(state["question"])
        return {
            "documents": result["documents"],
            "cypher": result["cypher"],
            "cypher_params": result["params"],
        }

    async def retrieve_vector_candidates(self, state: GraphState) -> Dict:
        question = state["question"]
        # 1. Extract entities to find subject
        _, extracted_data, _ = await cypher_builder.extract_entities_and_build_cypher(
            question
        )

        subject = cypher_builder.get_search_subject(extracted_data)
        query_to_use = subject if subject else question

        documents = await self._run_vector_retrieval(query_to_use)
        candidate_ids = [doc.metadata["id"] for doc in documents]

        return {"candidate_ids": candidate_ids, "extracted_data": extracted_data}

    async def filter_with_graph(self, state: GraphState) -> Dict:
        candidate_ids = state.get("candidate_ids")
        extracted_data = state.get("extracted_data")

        if not candidate_ids:
            return {"documents": [], "cypher": None}

        target_entity = extracted_data.get("target_entity", "Produit")
        entities = extracted_data.get("entities", [])

        cypher, params = await cypher_builder.build_cypher_from_entities(
            target_entity, entities, candidate_ids
        )

        if not cypher:
            return {"documents": [], "cypher": None}

        context = await clients.execute_cypher(cypher, params)
        docs = [
            Document(page_content=json.dumps(item, default=str)) for item in context
        ]

        return {"documents": docs, "cypher": cypher, "cypher_params": params}

    async def parallel_retrieve(self, state: GraphState) -> Dict:
        question = state["question"]
        vector_task = self._run_vector_retrieval(question)
        graph_task = self._run_graph_retrieval(question)
        vector_docs, graph_result = await asyncio.gather(vector_task, graph_task)

        return {
            "vector_documents": vector_docs,
            "graph_documents": graph_result["documents"],
            "cypher": graph_result["cypher"],
            "cypher_params": graph_result["params"],
        }

    async def merge_and_rerank(self, state: GraphState) -> Dict:
        vector_docs = state.get("vector_documents", [])
        graph_docs = state.get("graph_documents", [])

        # Simple merge (deduplication logic would go here)
        merged = vector_docs + graph_docs

        # Rerank using gRPC client
        doc_texts = [d.page_content for d in merged]
        if doc_texts:
            reranked_texts = await clients.rerank_documents(
                state["question"], doc_texts
            )
            # Map back to documents (simplified)
            final_docs = [Document(page_content=t) for t in reranked_texts]
        else:
            final_docs = []

        return {"documents": final_docs}

    async def grade_documents(self, state: GraphState) -> Dict:
        # Placeholder for grading logic (could use LLM to check relevance)
        # For now, pass through
        return {"documents": state["documents"]}

    def decide_to_generate(self, state: GraphState) -> Dict:
        return {"documents": state.get("documents", [])}

    def handle_no_documents(self, state: GraphState) -> Dict:
        return {
            "generation": "Je n'ai pas trouvé d'information permettant de répondre à votre question.",
            "documents": [],
        }

    async def generate(self, state: GraphState) -> Dict:
        documents = state.get("documents", [])
        doc_content = "\n\n".join([d.page_content for d in documents])

        generation = await llm_service.invoke_chain(
            ANSWER_GENERATION_TEMPLATE,
            {"context": doc_content, "question": state["question"]},
        )
        return {"generation": generation, "documents": documents}

    async def process_query(self, user_query: str, route: str = "") -> QueryResponse:
        inputs = {"question": user_query}
        if route:
            inputs["routing_decision"] = route

        final_state = await self.app.ainvoke(inputs)

        return QueryResponse(
            question=user_query,
            answer=final_state.get("generation"),
            retrieved_context=[
                d.page_content for d in final_state.get("documents", [])
            ],
            generated_cypher=final_state.get("cypher"),
            search_type=final_state.get("routing_decision"),
            cypher_params=final_state.get("cypher_params"),
        )


rag_service = AgenticRAGService()
