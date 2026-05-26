"""File-aware codebase indexing and dependency analysis."""

from dataclasses import dataclass, field

import networkx as nx

from app.services.ast_service import ASTService
from app.services.chunking_service import ChunkingService


@dataclass
class FileIndex:
    path: str
    language: str
    symbols: list[str]
    imports: list[str]
    dependencies: list[str]
    line_count: int
    chunks: list[dict] = field(default_factory=list)


@dataclass
class ProjectIndex:
    project_id: str
    files: dict[str, FileIndex]
    dependency_graph: dict[str, list[str]]
    module_graph: nx.DiGraph | None = None


class CodebaseService:
    def __init__(self) -> None:
        self.ast = ASTService()
        self.chunking = ChunkingService()

    def index_project(
        self,
        files: dict[str, str],
        project_id: str = "default",
    ) -> ProjectIndex:
        file_indices: dict[str, FileIndex] = {}
        graph = nx.DiGraph()

        for path, content in files.items():
            language = self._detect_language(path)
            analysis = self.ast.analyze(content, language)
            chunks = self.chunking.chunk(content, source=path, language=language)

            file_indices[path] = FileIndex(
                path=path,
                language=language,
                symbols=[s.name for s in analysis.symbols],
                imports=analysis.imports,
                dependencies=analysis.dependencies,
                line_count=analysis.line_count,
                chunks=[
                    {
                        "content": c.content,
                        "chunk_type": c.chunk_type,
                        "symbol_name": c.symbol_name,
                        "index": c.index,
                    }
                    for c in chunks
                ],
            )
            graph.add_node(path, symbols=file_indices[path].symbols)

        dep_graph: dict[str, list[str]] = {}
        for path, fi in file_indices.items():
            deps: list[str] = []
            for imp in fi.imports:
                matched = self._resolve_import(imp, files)
                deps.extend(matched)
                for dep in matched:
                    graph.add_edge(path, dep)
            dep_graph[path] = list(set(deps))

        return ProjectIndex(
            project_id=project_id,
            files=file_indices,
            dependency_graph=dep_graph,
            module_graph=graph,
        )

    def get_related_files(
        self,
        index: ProjectIndex,
        filepath: str,
        max_depth: int = 2,
    ) -> list[str]:
        if not index.module_graph or filepath not in index.module_graph:
            return []
        related: set[str] = set()
        for depth in range(1, max_depth + 1):
            for node in nx.single_source_shortest_path_length(
                index.module_graph, filepath, cutoff=depth
            ):
                if node != filepath:
                    related.add(node)
        return list(related)

    def build_context_for_file(
        self,
        index: ProjectIndex,
        filepath: str,
        max_files: int = 5,
    ) -> str:
        related = self.get_related_files(index, filepath)[:max_files]
        parts = [f"[Codebase context for {filepath}]"]
        if filepath in index.files:
            fi = index.files[filepath]
            parts.append(f"Symbols: {', '.join(fi.symbols[:20])}")
        for rel in related:
            if rel in index.files:
                fi = index.files[rel]
                parts.append(f"Related: {rel} ({', '.join(fi.symbols[:5])})")
        return "\n".join(parts)

    def _detect_language(self, path: str) -> str:
        ext_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".tsx": "typescript", ".jsx": "javascript", ".java": "java",
            ".go": "go", ".rs": "rust", ".rb": "ruby",
        }
        for ext, lang in ext_map.items():
            if path.endswith(ext):
                return lang
        return "text"

    def _resolve_import(self, imp: str, files: dict[str, str]) -> list[str]:
        matched: list[str] = []
        imp_path = imp.replace(".", "/")
        for path in files:
            if imp_path in path or path.endswith(f"{imp.split('.')[-1]}.py"):
                matched.append(path)
        return matched[:3]
