"""AST-based code analysis and compression."""

import ast
import re
from dataclasses import dataclass, field

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CodeSymbol:
    name: str
    kind: str  # function, class, method, import, variable
    lineno: int
    end_lineno: int
    signature: str | None = None
    docstring: str | None = None
    dependencies: list[str] = field(default_factory=list)


@dataclass
class ASTAnalysis:
    language: str
    symbols: list[CodeSymbol]
    imports: list[str]
    dependencies: list[str]
    line_count: int
    compressed_skeleton: str | None = None


class ASTService:
    def analyze(self, code: str, language: str = "python") -> ASTAnalysis:
        if language == "python":
            return self._analyze_python(code)
        return self._analyze_generic(code, language)

    def compress_code(self, code: str, language: str = "python", keep_signatures: bool = True) -> str:
        analysis = self.analyze(code, language)
        if analysis.compressed_skeleton:
            return analysis.compressed_skeleton
        if language == "python":
            return self._compress_python(code, keep_signatures)
        return self._compress_generic(code)

    def extract_symbols(self, code: str, language: str = "python") -> list[CodeSymbol]:
        return self.analyze(code, language).symbols

    def chunk_by_ast(self, code: str, language: str = "python") -> list[dict]:
        analysis = self.analyze(code, language)
        chunks: list[dict] = []
        lines = code.splitlines()

        for symbol in analysis.symbols:
            if symbol.kind in ("function", "class", "method"):
                start = max(0, symbol.lineno - 1)
                end = min(len(lines), symbol.end_lineno)
                chunk_content = "\n".join(lines[start:end])
                chunks.append({
                    "content": chunk_content,
                    "symbol_name": symbol.name,
                    "chunk_type": symbol.kind,
                    "start_line": symbol.lineno,
                    "end_line": symbol.end_lineno,
                    "dependencies": symbol.dependencies,
                })

        if not chunks:
            chunks.append({
                "content": code,
                "symbol_name": None,
                "chunk_type": "file",
                "start_line": 1,
                "end_line": len(lines),
                "dependencies": analysis.imports,
            })
        return chunks

    def _analyze_python(self, code: str) -> ASTAnalysis:
        symbols: list[CodeSymbol] = []
        imports: list[str] = []
        dependencies: list[str] = []

        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            logger.warning("python_ast_parse_failed", error=str(exc))
            return self._analyze_generic(code, "python")

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
                    dependencies.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.append(module)
                if module:
                    dependencies.append(module.split(".")[0])
                for alias in node.names:
                    imports.append(f"{module}.{alias.name}" if module else alias.name)
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                args = [a.arg for a in node.args.args]
                sig = f"def {node.name}({', '.join(args)})"
                doc = ast.get_docstring(node)
                symbols.append(CodeSymbol(
                    name=node.name,
                    kind="function",
                    lineno=node.lineno,
                    end_lineno=node.end_lineno or node.lineno,
                    signature=sig,
                    docstring=doc,
                    dependencies=[d.id for d in node.decorator_list if isinstance(d, ast.Name)],
                ))
            elif isinstance(node, ast.ClassDef):
                methods = [
                    n.name for n in node.body
                    if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
                ]
                doc = ast.get_docstring(node)
                symbols.append(CodeSymbol(
                    name=node.name,
                    kind="class",
                    lineno=node.lineno,
                    end_lineno=node.end_lineno or node.lineno,
                    signature=f"class {node.name}",
                    docstring=doc,
                    dependencies=methods,
                ))

        skeleton = self._build_python_skeleton(symbols, imports)
        return ASTAnalysis(
            language="python",
            symbols=symbols,
            imports=imports,
            dependencies=list(set(dependencies)),
            line_count=len(code.splitlines()),
            compressed_skeleton=skeleton,
        )

    def _build_python_skeleton(self, symbols: list[CodeSymbol], imports: list[str]) -> str:
        parts = ["# [AST-compressed skeleton]"]
        for imp in imports[:20]:
            parts.append(f"import {imp}")
        parts.append("")
        for sym in symbols:
            if sym.signature:
                parts.append(f"{sym.signature}: ...")
            if sym.docstring:
                parts.append(f'    """{sym.docstring[:100]}"""')
        return "\n".join(parts)

    def _compress_python(self, code: str, keep_signatures: bool) -> str:
        analysis = self._analyze_python(code)
        if keep_signatures and analysis.compressed_skeleton:
            return analysis.compressed_skeleton
        return self._compress_generic(code)

    def _analyze_generic(self, code: str, language: str) -> ASTAnalysis:
        symbols: list[CodeSymbol] = []
        imports: list[str] = []

        patterns = {
            "function": r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)",
            "class": r"^(?:export\s+)?class\s+(\w+)",
            "method": r"^\s+(?:async\s+)?(\w+)\s*\(",
            "import": r"^(?:import|from|require|use)\s+(.+)",
        }

        for i, line in enumerate(code.splitlines(), 1):
            for kind, pattern in patterns.items():
                match = re.match(pattern, line)
                if match:
                    name = match.group(1).strip().split()[0].strip("'\"{")
                    if kind == "import":
                        imports.append(name)
                    else:
                        symbols.append(CodeSymbol(
                            name=name, kind=kind, lineno=i, end_lineno=i,
                            signature=line.strip(),
                        ))

        return ASTAnalysis(
            language=language,
            symbols=symbols,
            imports=imports,
            dependencies=imports,
            line_count=len(code.splitlines()),
        )

    def _compress_generic(self, code: str) -> str:
        lines = code.splitlines()
        result: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                continue
            if re.match(r"^(def |class |function |import |from |export )", stripped):
                result.append(stripped if stripped.endswith(":") else stripped + " ...")
            elif stripped.endswith("{") or stripped.endswith("("):
                result.append(stripped)
            elif len(stripped) > 80:
                result.append(stripped[:80] + " ...")
        return "\n".join(result[:100])
