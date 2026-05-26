"""RAG pipeline endpoints."""

from fastapi import APIRouter, Depends

from app.api.deps import get_rag_service
from app.core.security import verify_jwt_or_api_key
from app.schemas import (
    RAGChunk,
    RAGIngestRequest,
    RAGIngestResponse,
    RAGQueryRequest,
    RAGQueryResponse,
)
from app.services.rag_service import RAGService

router = APIRouter(prefix="/rag", tags=["RAG"])


@router.post("/query", response_model=RAGQueryResponse)
async def rag_query(
    request: RAGQueryRequest,
    _auth: dict = Depends(verify_jwt_or_api_key),
    service: RAGService = Depends(get_rag_service),
) -> RAGQueryResponse:
    results = await service.query(
        query=request.query,
        collection_id=request.collection_id,
        top_k=request.top_k,
        rerank=request.rerank,
    )
    chunks = [
        RAGChunk(
            id=doc.id,
            content=doc.content,
            source=doc.source,
            score=score,
            chunk_index=doc.chunk_index,
        )
        for doc, score in results
    ]
    context = "\n\n".join(c.content for c in chunks)
    return RAGQueryResponse(
        chunks=chunks,
        query=request.query,
        context=context,
        total_found=len(chunks),
    )


@router.post("/ingest", response_model=RAGIngestResponse)
async def rag_ingest(
    request: RAGIngestRequest,
    _auth: dict = Depends(verify_jwt_or_api_key),
    service: RAGService = Depends(get_rag_service),
) -> RAGIngestResponse:
    count = await service.ingest(
        content=request.content,
        collection_id=request.collection_id,
        source=request.source,
        metadata=request.metadata,
    )
    return RAGIngestResponse(chunks_created=count, collection_id=request.collection_id)
