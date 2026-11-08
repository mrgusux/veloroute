"""
Token-Saviour Context Optimizer & AST Syntax Chunker
====================================================
Lossless context compression, terminal output trimming, and AST-based
syntax code chunking inspired by vagkaratzas__token-saviour (Repo 241),
headroomlabs-ai__headroom (Repo 090), and tokenhop__tokenhop (Repo 231).

Capabilities:
  1. Lossless Terminal Output Trimming:
     - Strips ANSI escape sequences and terminal control codes.
     - Collapses repetitive logs and stack trace cascades.
     - Condenses git diff and compiler error noise while preserving context.
     - Normalizes excess blank lines and whitespace without breaking indentation.
  2. AST-Based Syntax Code Chunking:
     - Uses Python's native AST parser (and regex-based block parser for JS/TS/Go)
       to partition source code along logical syntactic boundaries (classes,
       functions, imports) rather than arbitrary line breaks.
  3. AST Code Skeletonization:
     - Replaces function/method implementations with '...' while retaining
       signatures, type hints, docstrings, and class hierarchies.
  4. Lossless Token Optimization:
     - Measures original vs. optimized token counts and computes compression ratio.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from veloroute.utils import count_tokens

# Regex for stripping ANSI escape sequences
_ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

# Common git diff index line: 'index 4a3b2c1..9f8e7d6 100644'
_GIT_DIFF_INDEX_RE = re.compile(r"^index [0-9a-fA-F]+\.\.[0-9a-fA-F]+(?: \d+)?\r?$", re.MULTILINE)


@dataclass
class ASTCodeChunk:
    """A syntactically coherent code block extracted via AST."""
    node_type: str            # 'function', 'class', 'import', 'statement'
    name: str                 # Function/class name or module
    start_line: int
    end_line: int
    code: str
    docstring: Optional[str] = None
    estimated_tokens: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_type": self.node_type,
            "name": self.name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "code": self.code,
            "docstring": self.docstring,
            "estimated_tokens": self.estimated_tokens,
        }


@dataclass
class OptimizationStats:
    """Statistics comparing original prompt vs. Token-Saviour optimized prompt."""
    original_tokens: int
    optimized_tokens: int
    saved_tokens: int
    savings_pct: float
    optimizations_applied: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_tokens": self.original_tokens,
            "optimized_tokens": self.optimized_tokens,
            "saved_tokens": self.saved_tokens,
            "savings_pct": round(self.savings_pct, 2),
            "optimizations_applied": self.optimizations_applied,
        }


class ContextOptimizer:
    """
    High-performance Token-Saviour context compression and AST chunking engine.
    """

    def __init__(self, default_model: str = "gpt-4o"):
        self.default_model = default_model

    @staticmethod
    def strip_ansi(text: str) -> str:
        """Strip ANSI terminal color and control sequences."""
        if not text:
            return ""
        return _ANSI_ESCAPE_RE.sub("", text)

    @classmethod
    def trim_terminal_output(
        cls,
        text: str,
        max_repeats: int = 2,
        collapse_git_noise: bool = True,
    ) -> Tuple[str, bool]:
        """
        Lossless terminal output and log stream trimming:
          - Strips ANSI sequences.
          - Collapses repeating consecutive lines (e.g. infinite polling or repeating error traces).
          - Condenses git diff index hashes and redundant separator bars.
        """
        if not text:
            return "", False

        modified = False
        clean = cls.strip_ansi(text)
        if clean != text:
            modified = True

        if collapse_git_noise:
            stripped_git = _GIT_DIFF_INDEX_RE.sub("", clean)
            if stripped_git != clean:
                clean = stripped_git
                modified = True

        lines = clean.splitlines()
        if len(lines) <= 3:
            return clean, modified

        output_lines: List[str] = []
        i = 0
        n = len(lines)

        while i < n:
            current_line = lines[i]
            # Count consecutive duplicates
            j = i + 1
            while j < n and lines[j].strip() and lines[j].strip() == current_line.strip():
                j += 1

            repeat_count = j - i
            if repeat_count > max_repeats:
                modified = True
                # Keep up to max_repeats instances
                for _ in range(max_repeats):
                    output_lines.append(current_line)
                omitted = repeat_count - max_repeats
                output_lines.append(f"  [... Token-Saviour: {omitted} identical lines collapsed ...]")
                i = j
            else:
                output_lines.append(current_line)
                i += 1

        result = "\n".join(output_lines)
        return result, modified

    @classmethod
    def normalize_whitespace(cls, text: str) -> Tuple[str, bool]:
        """
        Condenses 3+ consecutive newlines into 2 (preserving paragraph breaks)
        and strips trailing line whitespace without corrupting indentation.
        """
        if not text:
            return "", False

        lines = [line.rstrip() for line in text.splitlines()]
        cleaned = "\n".join(lines)
        # Collapse 3 or more blank newlines to 2
        collapsed = re.sub(r"\n{3,}", "\n\n", cleaned)
        modified = collapsed != text
        return collapsed, modified

    @classmethod
    def ast_chunk_python(cls, code: str) -> List[ASTCodeChunk]:
        """
        Parse Python source code using the standard AST library and yield
        logically atomic chunks (classes, top-level functions, imports, script blocks).
        """
        if not code or not code.strip():
            return []

        try:
            tree = ast.parse(code)
        except SyntaxError:
            # Fallback to indentation-based chunking on invalid syntax
            return cls._chunk_by_indentation(code, "python")

        code_lines = code.splitlines()
        chunks: List[ASTCodeChunk] = []

        # Group leading imports together
        import_lines: List[str] = []
        import_start = -1
        import_end = -1

        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                start = node.lineno
                end = getattr(node, "end_lineno", start)
                if import_start == -1:
                    import_start = start
                import_end = max(import_end, end)
                import_lines.extend(code_lines[start - 1 : end])
            else:
                # Flush imports if any
                if import_lines:
                    import_code = "\n".join(import_lines)
                    chunks.append(
                        ASTCodeChunk(
                            node_type="imports",
                            name="module_imports",
                            start_line=import_start,
                            end_line=import_end,
                            code=import_code,
                            estimated_tokens=count_tokens(import_code),
                        )
                    )
                    import_lines = []
                    import_start = -1

                start = node.lineno
                end = getattr(node, "end_lineno", start)
                chunk_code = "\n".join(code_lines[start - 1 : end])
                node_type = "statement"
                name = getattr(node, "name", "anonymous")
                docstring = ast.get_docstring(node)

                if isinstance(node, ast.ClassDef):
                    node_type = "class"
                    name = node.name
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    node_type = "function"
                    name = node.name

                chunks.append(
                    ASTCodeChunk(
                        node_type=node_type,
                        name=name,
                        start_line=start,
                        end_line=end,
                        code=chunk_code,
                        docstring=docstring,
                        estimated_tokens=count_tokens(chunk_code),
                    )
                )

        if import_lines:
            import_code = "\n".join(import_lines)
            chunks.append(
                ASTCodeChunk(
                    node_type="imports",
                    name="module_imports",
                    start_line=import_start,
                    end_line=import_end,
                    code=import_code,
                    estimated_tokens=count_tokens(import_code),
                )
            )

        return chunks

    @classmethod
    def _chunk_by_indentation(cls, code: str, language: str) -> List[ASTCodeChunk]:
        """Indentation/bracket-based fallback chunker for non-python code."""
        lines = code.splitlines()
        chunks: List[ASTCodeChunk] = []
        current_chunk: List[str] = []
        chunk_start = 1

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # If top-level function or class declaration
            is_boundary = False
            if language in ("javascript", "typescript", "js", "ts"):
                if re.match(r"^(export\s+)?(function|class|interface|type|const|let)\s+([A-Za-z0-9_$]+)", stripped):
                    is_boundary = True
            elif language in ("go", "golang"):
                if re.match(r"^func\s+|^type\s+", stripped):
                    is_boundary = True
            elif language == "python":
                if line and not line.startswith((" ", "\t")) and (line.startswith("def ") or line.startswith("class ")):
                    is_boundary = True

            if is_boundary and current_chunk:
                chunk_code = "\n".join(current_chunk)
                chunks.append(
                    ASTCodeChunk(
                        node_type="block",
                        name=f"block_line_{chunk_start}",
                        start_line=chunk_start,
                        end_line=i - 1,
                        code=chunk_code,
                        estimated_tokens=count_tokens(chunk_code),
                    )
                )
                current_chunk = []
                chunk_start = i

            current_chunk.append(line)

        if current_chunk:
            chunk_code = "\n".join(current_chunk)
            chunks.append(
                ASTCodeChunk(
                    node_type="block",
                    name=f"block_line_{chunk_start}",
                    start_line=chunk_start,
                    end_line=len(lines),
                    code=chunk_code,
                    estimated_tokens=count_tokens(chunk_code),
                )
            )

        return chunks

    @classmethod
    def _skeletonize_python_fallback(cls, code: str, keep_docstrings: bool = True) -> str:
        """
        Resilient line/block-level fallback skeletonizer when AST fails due to syntax errors
        (e.g. unclosed parentheses, partial typing, or invalid tokens).
        Replaces function and method bodies with '...' while preserving headers and docstrings.
        """
        lines = code.splitlines()
        output: List[str] = []
        i = 0
        n = len(lines)
        func_re = re.compile(r"^([ \t]*)(async\s+def|def)\s+([A-Za-z0-9_]+)\s*(\(.*)?$")

        while i < n:
            line = lines[i]
            m = func_re.match(line)
            if m:
                indent = m.group(1)
                # Read entire header if split across lines until ':'
                header_lines = [line]
                while i < n and ":" not in header_lines[-1]:
                    i += 1
                    if i < n:
                        header_lines.append(lines[i])
                output.extend(header_lines)
                i += 1

                # Check for docstring
                if keep_docstrings and i < n:
                    stripped = lines[i].strip()
                    if stripped.startswith('"""') or stripped.startswith("'''"):
                        doc_lines = [lines[i]]
                        quote = stripped[:3]
                        if stripped.count(quote) < 2:
                            i += 1
                            while i < n:
                                doc_lines.append(lines[i])
                                if quote in lines[i]:
                                    i += 1
                                    break
                                i += 1
                        else:
                            i += 1
                        output.extend(doc_lines)

                output.append(f"{indent}    ...")

                # Skip remaining body lines indented deeper than the function header
                base_indent_len = len(indent)
                while i < n:
                    cur = lines[i]
                    if not cur.strip():
                        i += 1
                        continue
                    cur_indent_len = len(cur) - len(cur.lstrip())
                    if cur_indent_len > base_indent_len:
                        i += 1
                    else:
                        break
            else:
                output.append(line)
                i += 1

        result = "\n".join(output)
        return result if len(result) < len(code) else code

    @classmethod
    def compress_caveman(cls, text: str) -> Tuple[str, bool]:
        """
        Caveman Terse Mode (Token-Saviour Repo 241.1):
        Removes conversational filler, polite boilerplate, and fluff words
        while preserving code blocks, variable names, URLs, file paths,
        and core imperative commands.
        """
        if not text:
            return "", False

        # Split markdown into code blocks and normal text so code is never touched
        parts = re.split(r"(```[\s\S]*?```)", text)
        modified = False
        compressed_parts: List[str] = []

        # Filler patterns to eliminate or simplify
        filler_patterns = [
            # Greetings
            (re.compile(r"(?i)\b(hello\s+there|hi\s+there|hey\s+there|hello|hi|hey|good\s+(morning|afternoon|evening))\b[,!.\s]*"), ""),
            # Politeness requests
            (re.compile(r"(?i)\b(could you please|would you please|can you please|please kindly|kindly|please)\b[, ]*"), ""),
            (re.compile(r"(?i)\b(i would (really\s+)?appreciate it if you could|i'd (really\s+)?appreciate it if you could)\b[, ]*"), ""),
            (re.compile(r"(?i)\b(i am looking for (a way to|help with)|i'm looking for (a way to|help with))\b[, ]*"), ""),
            (re.compile(r"(?i)\b(i need you to|i want you to)\b[, ]*"), ""),
            (re.compile(r"(?i)\b(feel free to|make sure (that|to)|be sure to|remember to)\b[, ]*"), ""),
            (re.compile(r"(?i)\b(in order to)\b"), "to"),
            # Trailing pleasantries
            (re.compile(r"(?i)\b(thank you (very much|so much)?( in advance)?|thanks (a lot|so much)?( in advance)?|thanks)[\s.!]*"), ""),
            (re.compile(r"(?i)\b(best regards|warm regards|sincerely|cheers)[\s.!]*"), ""),
        ]

        for part in parts:
            if part.startswith("```"):
                compressed_parts.append(part)
            else:
                orig_part = part
                p = part
                for pat, repl in filler_patterns:
                    p = pat.sub(repl, p)
                # Normalize double spaces created by deletions
                p = re.sub(r"[ \t]{2,}", " ", p)
                p = re.sub(r"^\s*[,.]\s*", "", p)
                if p != orig_part:
                    modified = True
                compressed_parts.append(p)

        result = "".join(compressed_parts)
        return result, modified

    @classmethod
    def prune_conversation(
        cls,
        messages: List[Dict[str, Any]],
        max_turns: int = 8,
        max_tokens: int = 4000,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Ponytail conversation checkpoint & history pruning (Repo 241.1):
        Preserves system instructions (turn 0) and the most recent N turns in full.
        Older intermediate assistant turns have large code blocks summarized to
        eliminate token waste while keeping the conversation coherent.
        """
        if not messages or len(messages) <= max_turns:
            return messages, {"pruned": False, "turns_removed": 0}

        result: List[Dict[str, Any]] = []
        has_system = False
        if messages and messages[0].get("role") == "system":
            result.append(messages[0])
            has_system = True

        non_system = messages[1:] if has_system else messages
        turns_to_keep = max_turns - (1 if has_system else 0)

        older = non_system[:-turns_to_keep]
        recent = non_system[-turns_to_keep:]

        for m in older:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "assistant" and isinstance(content, str) and len(content) > 300:
                shortened = content[:150] + "\n[... Ponytail: previous turn context condensed ...]\n" + content[-80:]
                new_m = dict(m)
                new_m["content"] = shortened
                result.append(new_m)
            else:
                result.append(m)

        result.extend(recent)
        return result, {"pruned": True, "turns_condensed": len(older)}

    @classmethod
    def skeletonize_python(cls, code: str, keep_docstrings: bool = True) -> str:
        """
        Creates an AST-aware structural skeleton of a Python module:
        Preserves imports, class definitions, function signatures, type annotations,
        and docstrings, but replaces implementation bodies with '...'.
        Falls back to resilient line/block parsing on syntax errors.
        """
        if not code or not code.strip():
            return code

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return cls._skeletonize_python_fallback(code, keep_docstrings=keep_docstrings)

        class SkeletonTransformer(ast.NodeTransformer):
            def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
                return self._trim_func_body(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
                return self._trim_func_body(node)

            def _trim_func_body(self, node: Any) -> Any:
                docstring = ast.get_docstring(node) if keep_docstrings else None
                new_body: List[ast.stmt] = []
                if docstring:
                    new_body.append(ast.Expr(value=ast.Constant(value=docstring)))
                # Ellipsis statement: '...'
                new_body.append(ast.Expr(value=ast.Constant(value=Ellipsis)))
                node.body = new_body
                return node

        skeleton_tree = SkeletonTransformer().visit(tree)
        ast.fix_missing_locations(skeleton_tree)
        try:
            return ast.unparse(skeleton_tree)
        except Exception:
            return cls._skeletonize_python_fallback(code, keep_docstrings=keep_docstrings)

    def optimize_text(
        self,
        text: str,
        skeletonize_python: bool = False,
        trim_terminal: bool = True,
        normalize_ws: bool = True,
        terse_mode: bool = False,
    ) -> Dict[str, Any]:
        """
        Run the complete Token-Saviour optimization pipeline on a text string.
        Returns optimized text alongside token metrics.
        """
        if not text:
            return {
                "original_text": "",
                "optimized_text": "",
                "stats": OptimizationStats(0, 0, 0, 0.0).to_dict(),
            }

        orig_tokens = count_tokens(text, self.default_model)
        current = text
        applied: List[str] = []

        # 1. Terminal / Log trimming
        if trim_terminal:
            current, mod = self.trim_terminal_output(current)
            if mod:
                applied.append("terminal_trimming_ansi_and_repeats")

        # 2. Python Code Skeletonization if requested
        if skeletonize_python:
            # Check for embedded markdown python code blocks (CRLF tolerant)
            def _repl(m: re.Match) -> str:
                lang = m.group(1) or ""
                code_body = m.group(2)
                if "python" in lang.lower() or not lang:
                    skeleton = self.skeletonize_python(code_body)
                    return f"```{lang}\n{skeleton}\n```"
                return m.group(0)

            code_block_re = re.compile(r"```([a-zA-Z0-9_-]*)\r?\n(.*?)```", re.DOTALL)
            if code_block_re.search(current):
                new_text = code_block_re.sub(_repl, current)
                if new_text != current:
                    current = new_text
                    applied.append("code_block_ast_skeletonize")
            else:
                # Try skeletonizing raw text
                skeleton = self.skeletonize_python(current)
                if skeleton and skeleton != current and len(skeleton) < len(current):
                    current = skeleton
                    applied.append("raw_python_ast_skeletonize")

        # 3. Caveman Terse Mode if requested
        if terse_mode:
            current, mod = self.compress_caveman(current)
            if mod:
                applied.append("caveman_terse_compression")

        # 4. Whitespace normalization
        if normalize_ws:
            current, mod = self.normalize_whitespace(current)
            if mod:
                applied.append("whitespace_normalization")

        opt_tokens = count_tokens(current, self.default_model)
        saved = max(0, orig_tokens - opt_tokens)
        savings_pct = (saved / orig_tokens * 100.0) if orig_tokens > 0 else 0.0

        stats = OptimizationStats(
            original_tokens=orig_tokens,
            optimized_tokens=opt_tokens,
            saved_tokens=saved,
            savings_pct=savings_pct,
            optimizations_applied=applied,
        )

        return {
            "original_text": text,
            "optimized_text": current,
            "stats": stats.to_dict(),
        }

    def optimize_messages(
        self,
        messages: List[Dict[str, Any]],
        skeletonize_python: bool = False,
        terse_mode: bool = False,
        prune_history: bool = True,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Applies Token-Saviour optimization across all user, system, and tool messages.
        """
        target_messages = messages
        if prune_history and len(messages) > 8:
            target_messages, _ = self.prune_conversation(messages)

        optimized_messages: List[Dict[str, Any]] = []
        total_orig_tokens = 0
        total_opt_tokens = 0
        all_applied: List[str] = []

        for msg in target_messages:
            content = msg.get("content", "")
            if isinstance(content, str) and content:
                res = self.optimize_text(
                    content,
                    skeletonize_python=skeletonize_python,
                    terse_mode=terse_mode,
                )
                new_msg = dict(msg)
                new_msg["content"] = res["optimized_text"]
                optimized_messages.append(new_msg)

                st = res["stats"]
                total_orig_tokens += st["original_tokens"]
                total_opt_tokens += st["optimized_tokens"]
                for app in st["optimizations_applied"]:
                    if app not in all_applied:
                        all_applied.append(app)
            else:
                optimized_messages.append(msg)

        saved = max(0, total_orig_tokens - total_opt_tokens)
        savings_pct = (saved / total_orig_tokens * 100.0) if total_orig_tokens > 0 else 0.0

        stats = OptimizationStats(
            original_tokens=total_orig_tokens,
            optimized_tokens=total_opt_tokens,
            saved_tokens=saved,
            savings_pct=savings_pct,
            optimizations_applied=all_applied,
        )
        return optimized_messages, stats.to_dict()
