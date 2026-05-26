"""Semantic memory endpoints."""

from fastapi import APIRouter, Depends

from app.api.deps import get_memory_service
from app.core.security import verify_jwt_or_api_key
from app.schemas import (
    MemoryItem,
    MemorySaveRequest,
    MemorySaveResponse,
    MemorySearchRequest,
    MemorySearchResponse,
)
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/memory", tags=["Memory"])


@router.post("/save", response_model=MemorySaveResponse)
async def save_memory(
    request: MemorySaveRequest,
    _auth: dict = Depends(verify_jwt_or_api_key),
    service: MemoryService = Depends(get_memory_service),
) -> MemorySaveResponse:
    memory = await service.save_memory(
        content=request.content,
        memory_type=request.memory_type,
        user_id=request.user_id,
        session_id=request.session_id,
        metadata=request.metadata,
    )
    return MemorySaveResponse(
        id=memory.id,
        content=memory.content,
        summary=memory.summary,
        memory_type=memory.memory_type.value,
        created_at=memory.created_at,
    )


@router.post("/search", response_model=MemorySearchResponse)
async def search_memory(
    request: MemorySearchRequest,
    _auth: dict = Depends(verify_jwt_or_api_key),
    service: MemoryService = Depends(get_memory_service),
) -> MemorySearchResponse:
    results = await service.semantic_search(
        query=request.query,
        user_id=request.user_id,
        top_k=request.top_k,
        memory_types=request.memory_types,
        min_score=request.min_score,
    )
    items = [
        MemoryItem(
            id=mem.id,
            content=mem.content,
            summary=mem.summary,
            memory_type=mem.memory_type.value,
            relevance_score=score,
            metadata=mem.metadata_,
            created_at=mem.created_at,
        )
        for mem, score in results
    ]
    return MemorySearchResponse(
        memories=items, query=request.query, total_found=len(items)
    )
