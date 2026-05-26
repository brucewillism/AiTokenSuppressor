"""Context graph memory with entity relationships."""

import re
import uuid
from dataclasses import dataclass, field

import networkx as nx

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GraphEntity:
    id: str
    label: str
    entity_type: str
    weight: float = 1.0
    metadata: dict = field(default_factory=dict)


@dataclass
class GraphRelation:
    source: str
    target: str
    relationship: str
    weight: float = 1.0


ENTITY_PATTERNS = {
    "framework": r"\b(Spring Boot|FastAPI|Django|React|Vue|Angular|Express|Flask)\b",
    "database": r"\b(PostgreSQL|MySQL|MongoDB|Redis|Oracle|SQLite|pgvector)\b",
    "protocol": r"\b(JWT|OAuth2|REST|GraphQL|gRPC|WebSocket)\b",
    "tool": r"\b(Docker|Kubernetes|Celery|Ollama|Prometheus|Grafana|Nginx)\b",
    "language": r"\b(Python|JavaScript|TypeScript|Java|Go|Rust|Ruby)\b",
}


RELATIONSHIP_PATTERNS = [
    (r"(\w[\w\s]*?)\s+(?:uses|using|with|via)\s+(\w[\w\s]*)", "uses"),
    (r"(\w[\w\s]*?)\s+(?:depends on|requires)\s+(\w[\w\s]*)", "depends_on"),
    (r"(\w[\w\s]*?)\s+(?:integrates with|connected to)\s+(\w[\w\s]*)", "integrates"),
    (r"(\w[\w\s]*?)\s*→\s*(\w[\w\s]*)", "relates_to"),
    (r"(\w[\w\s]*?)\s*->\s*(\w[\w\s]*)", "relates_to"),
]


class ContextGraphService:
    def __init__(self) -> None:
        self._graphs: dict[str, nx.DiGraph] = {}

    def get_graph(self, user_id: str) -> nx.DiGraph:
        if user_id not in self._graphs:
            self._graphs[user_id] = nx.DiGraph()
        return self._graphs[user_id]

    def extract_entities(self, text: str) -> list[GraphEntity]:
        entities: list[GraphEntity] = []
        seen: set[str] = set()

        for entity_type, pattern in ENTITY_PATTERNS.items():
            for match in re.finditer(pattern, text, re.IGNORECASE):
                label = match.group(1).strip()
                key = label.lower()
                if key not in seen:
                    seen.add(key)
                    entities.append(GraphEntity(
                        id=key.replace(" ", "_"),
                        label=label,
                        entity_type=entity_type,
                    ))

        capitalized = re.findall(r"\b[A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)*\b", text)
        for cap in capitalized[:15]:
            key = cap.lower()
            if key not in seen and len(cap) > 2:
                seen.add(key)
                entities.append(GraphEntity(
                    id=key.replace(" ", "_"),
                    label=cap,
                    entity_type="concept",
                ))

        return entities

    def extract_relationships(self, text: str, entities: list[GraphEntity]) -> list[GraphRelation]:
        relations: list[GraphRelation] = []
        entity_labels = {e.label.lower(): e.id for e in entities}

        for pattern, rel_type in RELATIONSHIP_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                source = match.group(1).strip().lower()
                target = match.group(2).strip().lower()
                source_id = entity_labels.get(source, source.replace(" ", "_"))
                target_id = entity_labels.get(target, target.replace(" ", "_"))
                relations.append(GraphRelation(
                    source=source_id, target=target_id, relationship=rel_type,
                ))

        for i, e1 in enumerate(entities):
            for e2 in entities[i + 1:]:
                if e1.label.lower() in text.lower() and e2.label.lower() in text.lower():
                    dist = abs(text.lower().find(e1.label.lower()) - text.lower().find(e2.label.lower()))
                    if dist < 200:
                        relations.append(GraphRelation(
                            source=e1.id, target=e2.id, relationship="co_occurs", weight=0.5,
                        ))
        return relations

    def ingest(self, user_id: str, content: str, entities: list[str] | None = None) -> list[GraphEntity]:
        graph = self.get_graph(user_id)
        extracted = self.extract_entities(content)

        if entities:
            for label in entities:
                eid = label.lower().replace(" ", "_")
                if not any(e.id == eid for e in extracted):
                    extracted.append(GraphEntity(id=eid, label=label, entity_type="manual"))

        relations = self.extract_relationships(content, extracted)

        for entity in extracted:
            if entity.id not in graph:
                graph.add_node(entity.id, label=entity.label, type=entity.entity_type, weight=entity.weight)
            else:
                graph.nodes[entity.id]["weight"] = graph.nodes[entity.id].get("weight", 1) + 0.1

        for rel in relations:
            if rel.source in graph and rel.target in graph:
                graph.add_edge(rel.source, rel.target, relationship=rel.relationship, weight=rel.weight)

        return extracted

    def traverse(self, user_id: str, query: str, max_depth: int = 2) -> tuple[list[GraphEntity], list[GraphRelation]]:
        graph = self.get_graph(user_id)
        query_entities = self.extract_entities(query)
        if not query_entities:
            return [], []

        visited_nodes: set[str] = set()
        visited_edges: set[str] = set()
        result_entities: list[GraphEntity] = []
        result_relations: list[GraphRelation] = []

        for qe in query_entities:
            if qe.id in graph:
                for node in nx.single_source_shortest_path_length(graph, qe.id, cutoff=max_depth):
                    if node not in visited_nodes:
                        visited_nodes.add(node)
                        data = graph.nodes[node]
                        result_entities.append(GraphEntity(
                            id=node, label=data.get("label", node),
                            entity_type=data.get("type", "concept"),
                            weight=data.get("weight", 1.0),
                        ))

        for u, v, data in graph.edges(data=True):
            if u in visited_nodes and v in visited_nodes:
                edge_key = f"{u}-{v}"
                if edge_key not in visited_edges:
                    visited_edges.add(edge_key)
                    result_relations.append(GraphRelation(
                        source=u, target=v,
                        relationship=data.get("relationship", "relates_to"),
                        weight=data.get("weight", 1.0),
                    ))

        result_entities.sort(key=lambda e: e.weight, reverse=True)
        return result_entities, result_relations

    def build_context(self, user_id: str, query: str, max_depth: int = 2) -> str:
        entities, relations = self.traverse(user_id, query, max_depth)
        if not entities:
            return ""

        parts = ["[Context graph]"]
        for entity in entities[:10]:
            parts.append(f"- {entity.label} ({entity.entity_type})")
        for rel in relations[:10]:
            parts.append(f"  {rel.source} --[{rel.relationship}]--> {rel.target}")

        return "\n".join(parts)

    def rank_entities(self, user_id: str) -> list[GraphEntity]:
        graph = self.get_graph(user_id)
        if not graph:
            return []
        centrality = nx.degree_centrality(graph)
        entities = [
            GraphEntity(
                id=node,
                label=data.get("label", node),
                entity_type=data.get("type", "concept"),
                weight=centrality.get(node, 0) + data.get("weight", 0),
            )
            for node, data in graph.nodes(data=True)
        ]
        entities.sort(key=lambda e: e.weight, reverse=True)
        return entities

    def to_response(self, entities: list[GraphEntity], relations: list[GraphRelation]) -> dict:
        return {
            "nodes": [
                {"id": e.id, "label": e.label, "entity_type": e.entity_type, "weight": e.weight}
                for e in entities
            ],
            "edges": [
                {"source": r.source, "target": r.target, "relationship": r.relationship, "weight": r.weight}
                for r in relations
            ],
        }
