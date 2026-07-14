import numpy as np

from app.agents.agentic_workflow import AgenticRAGOrchestrator
from app.agents.streaming_workflow import StreamingOrchestrator
from app.retrieval.hybrid_retriever import RetrievalResult
from app.retrieval.index_store import IndexStore
from app.schemas.document import Chunk


class DeterministicEmbedder:
    def __init__(self):
        self.calls = 0

    def embed_single(self, text: str) -> np.ndarray:
        self.calls += 1
        vector = np.zeros(4, dtype=np.float32)
        vector[0] = 1.0
        return vector


def _build_index(chunks: list[Chunk]) -> IndexStore:
    embeddings = np.zeros((len(chunks), 4), dtype=np.float32)
    embeddings[:, 0] = 1.0
    store = IndexStore()
    store.build_indexes(chunks, embeddings)
    return store


class SingleResultRetriever:
    def __init__(self, result: RetrievalResult):
        self.result = result
        self.calls = 0

    def retrieve(self, query: str) -> list[RetrievalResult]:
        self.calls += 1
        return [self.result]

    def retrieve_for_sub_queries(self, queries: list[str]) -> list[RetrievalResult]:
        self.calls += 1
        return [self.result]


class StaticRetriever:
    def __init__(self, results: list[RetrievalResult]):
        self.results = results

    def retrieve(self, query: str) -> list[RetrievalResult]:
        return self.results

    def retrieve_for_sub_queries(self, queries: list[str]) -> list[RetrievalResult]:
        return self.results


class CoverageGapRetriever:
    def __init__(
        self,
        first_result: RetrievalResult,
        targeted_result: RetrievalResult,
    ):
        self.first_result = first_result
        self.targeted_result = targeted_result
        self.calls = []

    def retrieve_for_sub_queries(self, queries: list[str]) -> list[RetrievalResult]:
        self.calls.append(("multi", tuple(queries)))
        return [self.first_result]

    def retrieve(self, query: str) -> list[RetrievalResult]:
        self.calls.append(("single", query))
        if "notifiable" in query.lower():
            return [self.targeted_result]
        return [self.first_result]


class EmptyRetriever:
    def __init__(self, index_store: IndexStore):
        self.index_store = index_store
        self.calls = 0

    def retrieve(self, query: str) -> list[RetrievalResult]:
        self.calls += 1
        return []

    def retrieve_for_sub_queries(self, queries: list[str]) -> list[RetrievalResult]:
        self.calls += 1
        return []


def test_injected_index_store_builds_a_ready_retriever():
    store = _build_index([
        Chunk(
            chunk_id="c1",
            document_id="d1",
            source_path="rules.md",
            text="Listing applicants must satisfy the applicable requirements.",
        )
    ])

    orchestrator = AgenticRAGOrchestrator(
        index_store=store,
        embedder=DeterministicEmbedder(),
        use_llm_planner=False,
    )

    assert orchestrator.is_ready() is True


def test_retriever_only_injection_retries_and_records_empty_rounds():
    store = _build_index([
        Chunk(
            chunk_id="unused",
            document_id="d1",
            source_path="rules.md",
            text="Unused test chunk",
        )
    ])
    retriever = EmptyRetriever(store)
    orchestrator = AgenticRAGOrchestrator(
        retriever=retriever,
        use_llm_planner=False,
    )

    assert orchestrator.is_ready() is True

    result = orchestrator.process_query(
        "Explain disclosure obligations",
        use_llm_planner=False,
    )

    assert retriever.calls == 2
    assert result["coverage_assessment"]["coverage_score"] == 0.0
    assert [record["round_number"] for record in result["retrieval_rounds"]] == [1, 2]
    assert all(record["chunk_ids"] == [] for record in result["retrieval_rounds"])
    assert all(record["coverage_after"] == 0.0 for record in result["retrieval_rounds"])


def test_streaming_orchestrator_accepts_a_complete_retriever():
    store = _build_index([
        Chunk(
            chunk_id="unused",
            document_id="d1",
            source_path="rules.md",
            text="Unused test chunk",
        )
    ])

    orchestrator = StreamingOrchestrator(retriever=EmptyRetriever(store))

    assert orchestrator.is_ready() is True


def test_obligation_summary_uses_dense_score_for_coverage():
    query = "Summarize disclosure obligations for listed issuers"
    store = _build_index([
        Chunk(
            chunk_id="dense-match",
            document_id="d1",
            source_path="rules.md",
            text=query,
        )
    ])
    chunk = store.get_chunk_by_id("dense-match")
    retriever = SingleResultRetriever(RetrievalResult(
        chunk_id="dense-match",
        chunk=chunk,
        score=0.0,
        bm25_score=0.0,
        dense_score=1.0,
    ))
    orchestrator = AgenticRAGOrchestrator(
        index_store=store,
        retriever=retriever,
        use_llm_planner=False,
    )

    result = orchestrator.process_query(query, use_llm_planner=False)

    assert result["coverage_assessment"]["score_strategy"] == "dense"
    assert result["coverage_assessment"]["coverage_score"] == 1.0
    assert retriever.calls == 1


def test_answer_citations_use_only_selected_evidence():
    query = "Explain listing requirements"
    chunks = [
        Chunk(
            chunk_id=f"c{i}",
            document_id="d1",
            source_path="rules.md",
            text=f"{query}: supporting provision {i}",
            rule_number=f"1.{i}",
        )
        for i in range(1, 7)
    ]
    store = _build_index(chunks)
    results = [
        RetrievalResult(
            chunk_id=chunk.chunk_id,
            chunk=chunk,
            score=1.0 - index / 10,
            bm25_score=1.0,
            dense_score=1.0,
        )
        for index, chunk in enumerate(chunks)
    ]
    orchestrator = AgenticRAGOrchestrator(
        index_store=store,
        retriever=StaticRetriever(results),
        use_llm_planner=False,
    )

    result = orchestrator.process_query(query, use_llm_planner=False)

    selected_ids = {
        item["chunk_id"]
        for item in result["selected_evidence"]["selected_chunks"]
    }
    citation_ids = {
        citation.chunk_id if hasattr(citation, "chunk_id") else citation["chunk_id"]
        for citation in result["citations"]
    }
    assert len(selected_ids) == 5
    assert citation_ids == selected_ids


def test_second_retrieval_targets_only_the_coverage_gap():
    query = "Compare disclosure requirements for connected and notifiable transactions"
    chunks = [
        Chunk(
            chunk_id="connected",
            document_id="d1",
            source_path="chapter-14a.md",
            text="Compare disclosure requirements for connected parties.",
        ),
        Chunk(
            chunk_id="notifiable",
            document_id="d2",
            source_path="chapter-14.md",
            text="Notifiable transactions are subject to classification requirements.",
        ),
    ]
    store = _build_index(chunks)
    first_result = RetrievalResult(
        chunk_id="connected",
        chunk=chunks[0],
        score=0.9,
        bm25_score=0.9,
        dense_score=0.9,
    )
    targeted_result = RetrievalResult(
        chunk_id="notifiable",
        chunk=chunks[1],
        score=0.9,
        bm25_score=0.9,
        dense_score=0.9,
    )
    retriever = CoverageGapRetriever(first_result, targeted_result)
    orchestrator = AgenticRAGOrchestrator(
        index_store=store,
        retriever=retriever,
        use_llm_planner=False,
    )

    result = orchestrator.process_query(query, use_llm_planner=False)

    assert retriever.calls == [
        (
            "multi",
            (
                "Compare disclosure requirements for connected",
                "notifiable transactions",
            ),
        ),
        ("single", "notifiable transactions"),
    ]
    assert {chunk["chunk_id"] for chunk in result["retrieved_chunks"]} == {
        "connected",
        "notifiable",
    }
    assert result["coverage_assessment"]["coverage_score"] == 1.0
    assert result["retrieval_rounds"] == [
        {
            "round_number": 1,
            "queries": [
                "Compare disclosure requirements for connected",
                "notifiable transactions",
            ],
            "chunk_ids": ["connected"],
            "coverage_before": 0.0,
            "coverage_after": 0.5,
        },
        {
            "round_number": 2,
            "queries": ["notifiable transactions"],
            "chunk_ids": ["notifiable"],
            "coverage_before": 0.5,
            "coverage_after": 1.0,
        },
    ]
