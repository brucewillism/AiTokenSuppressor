"""Semantic and AST-based diff engine."""

import difflib
from dataclasses import dataclass, field

from app.services.ast_service import ASTService


@dataclass
class DiffHunk:
    type: str  # add, remove, modify, equal
    old_content: str
    new_content: str
    symbol_name: str | None = None
    line_range: tuple[int, int] | None = None


@dataclass
class SemanticDiff:
    hunks: list[DiffHunk]
    patch: str
    delta_tokens_estimate: int
    change_ratio: float
    changed_symbols: list[str] = field(default_factory=list)


class DiffService:
    def __init__(self) -> None:
        self.ast = ASTService()

    def diff(self, old: str, new: str, language: str = "python") -> SemanticDiff:
        if language == "python":
            ast_diff = self._ast_diff(old, new, language)
            if ast_diff.changed_symbols:
                return ast_diff
        return self._text_diff(old, new)

    def incremental_context(self, previous: str, current: str, language: str = "python") -> str:
        diff = self.diff(previous, current, language)
        if diff.change_ratio < 0.1:
            return current

        parts = ["[Incremental context update - only changes]"]
        for hunk in diff.hunks:
            if hunk.type == "add":
                parts.append(f"+ ADDED ({hunk.symbol_name or 'block'}):\n{hunk.new_content}")
            elif hunk.type == "modify":
                parts.append(
                    f"~ MODIFIED ({hunk.symbol_name or 'block'}):\n"
                    f"--- old ---\n{hunk.old_content[:500]}\n"
                    f"+++ new +++\n{hunk.new_content[:500]}"
                )
            elif hunk.type == "remove":
                parts.append(f"- REMOVED ({hunk.symbol_name or 'block'})")

        if len(parts) == 1:
            return diff.patch
        return "\n\n".join(parts)

    def _ast_diff(self, old: str, new: str, language: str) -> SemanticDiff:
        old_analysis = self.ast.analyze(old, language)
        new_analysis = self.ast.analyze(new, language)

        old_symbols = {s.name: s for s in old_analysis.symbols}
        new_symbols = {s.name: s for s in new_analysis.symbols}

        hunks: list[DiffHunk] = []
        changed: list[str] = []

        for name, new_sym in new_symbols.items():
            if name not in old_symbols:
                hunks.append(DiffHunk(
                    type="add", old_content="", new_content=new_sym.signature or name,
                    symbol_name=name, line_range=(new_sym.lineno, new_sym.end_lineno),
                ))
                changed.append(name)
            elif old_symbols[name].signature != new_sym.signature:
                hunks.append(DiffHunk(
                    type="modify",
                    old_content=old_symbols[name].signature or "",
                    new_content=new_sym.signature or "",
                    symbol_name=name,
                ))
                changed.append(name)

        for name in old_symbols:
            if name not in new_symbols:
                hunks.append(DiffHunk(
                    type="remove",
                    old_content=old_symbols[name].signature or name,
                    new_content="",
                    symbol_name=name,
                ))
                changed.append(name)

        patch = self._build_patch(hunks)
        total = max(len(old), len(new), 1)
        delta = sum(len(h.new_content) + len(h.old_content) for h in hunks)

        return SemanticDiff(
            hunks=hunks,
            patch=patch,
            delta_tokens_estimate=delta // 4,
            change_ratio=delta / total,
            changed_symbols=changed,
        )

    def _text_diff(self, old: str, new: str) -> SemanticDiff:
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        differ = difflib.unified_diff(old_lines, new_lines, lineterm="")
        patch_lines = list(differ)
        patch = "".join(patch_lines)

        matcher = difflib.SequenceMatcher(None, old, new)
        hunks: list[DiffHunk] = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            hunks.append(DiffHunk(
                type={"insert": "add", "delete": "remove", "replace": "modify"}.get(tag, tag),
                old_content=old[i1:i2],
                new_content=new[j1:j2],
            ))

        return SemanticDiff(
            hunks=hunks,
            patch=patch,
            delta_tokens_estimate=len(patch) // 4,
            change_ratio=1.0 - matcher.ratio(),
        )

    def _build_patch(self, hunks: list[DiffHunk]) -> str:
        lines: list[str] = []
        for h in hunks:
            prefix = {"add": "+", "remove": "-", "modify": "~"}.get(h.type, "?")
            content = h.new_content or h.old_content
            lines.append(f"{prefix} [{h.symbol_name or 'block'}] {content}")
        return "\n".join(lines)
