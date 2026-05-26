"""Advanced API endpoints: benchmark, heatmap, graph, codebase, stream."""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import get_optimize_service
from app.core.security import verify_jwt_or_api_key
from app.schemas import (
    BenchmarkRequest,
    BenchmarkResponse,
    BenchmarkResult,
    CodebaseIndexRequest,
    CodebaseIndexResponse,
    GraphQueryRequest,
    GraphResponse,
    GraphEdge,
    GraphNode,
    HeatmapRequest,
    HeatmapResponse,
    HeatmapSegment,
    StreamCompressRequest,
)
from app.services.benchmark_service import BenchmarkService
from app.services.codebase_service import CodebaseService
from app.services.context_graph_service import ContextGraphService
from app.services.optimize_service import OptimizeService
from app.services.rag_service import RAGService
from app.services.streaming_service import StreamingService
from app.services.token_heatmap_service import TokenHeatmapService

router = APIRouter(prefix="/advanced", tags=["Advanced"])


@router.post("/benchmark", response_model=BenchmarkResponse)
async def run_benchmark(
    request: BenchmarkRequest,
    _auth: dict = Depends(verify_jwt_or_api_key),
    service: OptimizeService = Depends(get_optimize_service),
) -> BenchmarkResponse:
    benchmark = BenchmarkService()
    msg_dicts = [m.model_dump() for m in request.messages]
    entries, best_strategy, best_score = await benchmark.run(
        msg_dicts, request.strategies, request.target_model,
    )
    return BenchmarkResponse(
        results=[BenchmarkResult(**e.__dict__) for e in entries],
        best_strategy=best_strategy,
        best_balance_score=best_score,
    )


@router.post("/heatmap", response_model=HeatmapResponse)
async def token_heatmap(
    request: HeatmapRequest,
    _auth: dict = Depends(verify_jwt_or_api_key),
) -> HeatmapResponse:
    heatmap = TokenHeatmapService()
    msg_dicts = [m.model_dump() for m in request.messages]
    data = heatmap.generate(msg_dicts, request.target_model)
    return HeatmapResponse(
        total_tokens=data["total_tokens"],
        segments=[HeatmapSegment(**s) for s in data["segments"]],
        hotspots=data["hotspots"],
    )


@router.post("/graph/query", response_model=GraphResponse)
async def query_context_graph(
    request: GraphQueryRequest,
    _auth: dict = Depends(verify_jwt_or_api_key),
) -> GraphResponse:
    graph = ContextGraphService()
    graph.ingest(request.user_id, request.query)
    entities, relations = graph.traverse(request.user_id, request.query, request.max_depth)
    context = graph.build_context(request.user_id, request.query, request.max_depth)
    return GraphResponse(
        nodes=[GraphNode(**{"id": e.id, "label": e.label, "entity_type": e.entity_type, "weight": e.weight}) for e in entities],
        edges=[GraphEdge(**{"source": r.source, "target": r.target, "relationship": r.relationship, "weight": r.weight}) for r in relations],
        context_summary=context,
    )


@router.post("/codebase/index", response_model=CodebaseIndexResponse)
async def index_codebase(
    request: CodebaseIndexRequest,
    _auth: dict = Depends(verify_jwt_or_api_key),
    service: OptimizeService = Depends(get_optimize_service),
) -> CodebaseIndexResponse:
    codebase = CodebaseService()
    index = codebase.index_project(request.files, request.project_id)

    rag = RAGService(service.db)
    chunks_created = 0
    chunk_types: dict[str, int] = {}
    symbols_found = 0

    for path, fi in index.files.items():
        symbols_found += len(fi.symbols)
        count = await rag.ingest(
            "\n\n".join(c["content"] for c in fi.chunks),
            collection_id=request.collection_id,
            source=path,
            metadata={"symbols": fi.symbols, "language": fi.language},
            chunk_by_ast=True,
            language=fi.language,
        )
        chunks_created += count
        for chunk in fi.chunks:
            ct = chunk["chunk_type"]
            chunk_types[ct] = chunk_types.get(ct, 0) + 1

    return CodebaseIndexResponse(
        files_indexed=len(index.files),
        symbols_found=symbols_found,
        chunks_created=chunks_created,
        dependencies={k: v for k, v in list(index.dependency_graph.items())[:50]},
    )


@router.post("/stream/compress")
async def stream_compress(
    request: StreamCompressRequest,
    _auth: dict = Depends(verify_jwt_or_api_key),
):
    streaming = StreamingService()
    msg_dicts = [m.model_dump() for m in request.messages]

    async def event_generator():
        import json
        async for chunk in streaming.compress_stream(msg_dicts, request.strategy, request.chunk_size):
            yield json.dumps({
                "index": chunk.index,
                "tokens": chunk.tokens,
                "operation": chunk.operation,
                "cumulative_savings": chunk.cumulative_savings,
                "messages": chunk.messages,
            }) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")
