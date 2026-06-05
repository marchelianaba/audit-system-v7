"""DSL parser untuk Mesin Kriteria CACM.

Dua DSL kecil yang diparse di sini:

1. **Metric expression** — dipakai di `metric.expression` YAML kriteria.
   Bentuk: `<fn>(<field>[ WHERE <cond>]) [op <fn>(...)] ...`
   Functions: sum, avg, count, ratio, max, min.
   Operator: `+`, `-`, `*`, `/`, parens.
   Field: `data.<key>` (key di CacmObservasi.data JSONB).
   Condition: `<field> <cmp> <literal>` dengan `AND`/`OR`/`NOT`.

2. **Threshold expression** — dipakai di `thresholds[].condition` YAML.
   Bentuk: comparison ops atas variabel `value` (hasil metric).
   Mis. `">=60"`, `">=40 AND <60"`, `"<40 OR (>=80 AND <90)"`.

Implementasi:
- Aman: TIDAK pakai `eval()` mentah. Tokenize → recursive descent parser →
  AST → interpret atas data.
- Deterministik: same input → same output. No I/O, no LLM.
- Toleran: error mudah dibaca (line+col, jenis token yang salah).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Tokenizer (shared between metric & threshold)
# ---------------------------------------------------------------------------

_TOKEN_PATTERNS = [
    ("WS", r"\s+"),
    ("NUMBER", r"\d+(?:\.\d+)?"),
    ("STRING", r'"[^"]*"|\'[^\']*\''),
    # Functions
    ("KW", r"\b(?:sum|avg|count|ratio|max|min|delta|WHERE|AND|OR|NOT|TRUE|FALSE|None|NULL)\b"),
    # Identifiers + dotted (data.pagu / data.metode)
    ("IDENT", r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*"),
    # Operators (multi-char first)
    ("OP", r"==|!=|>=|<=|>|<|\+|\-|\*|/|\(|\)"),
    ("COMMA", r","),
]
_TOKEN_RE = re.compile("|".join(f"(?P<{name}>{pat})" for name, pat in _TOKEN_PATTERNS))


@dataclass
class Token:
    type: str
    value: str
    pos: int

    def __repr__(self) -> str:
        return f"Token({self.type}, {self.value!r})"


class DSLError(Exception):
    """Diraise saat parsing/eval gagal. Pesan termasuk posisi."""


def tokenize(s: str) -> list[Token]:
    out: list[Token] = []
    pos = 0
    while pos < len(s):
        m = _TOKEN_RE.match(s, pos)
        if not m:
            raise DSLError(f"karakter tak dikenal di posisi {pos}: {s[pos:pos+20]!r}")
        kind = m.lastgroup
        if kind != "WS":
            val = m.group()
            # Normalize OP `\(` & `\)` (dari regex escape)
            if kind == "OP" and val.startswith("\\"):
                val = val[1:]
            out.append(Token(kind, val, pos))  # type: ignore[arg-type]
        pos = m.end()
    return out


# ---------------------------------------------------------------------------
# AST nodes (deliberately simple — interpret by recursion)
# ---------------------------------------------------------------------------

@dataclass
class Num:
    val: float

@dataclass
class Str:
    val: str

@dataclass
class Bool:
    val: bool

@dataclass
class Null:
    """Literal None / NULL / TRUE/FALSE handler."""

@dataclass
class FieldRef:
    """Reference ke field row (mis. data.pagu)."""
    path: list[str]  # ['data', 'pagu']

@dataclass
class BinOp:
    op: str
    left: Any
    right: Any

@dataclass
class UnaryOp:
    op: str
    operand: Any

@dataclass
class FnCall:
    name: str                 # sum/avg/count/ratio/max/min/delta
    arg: Any | None           # FieldRef atau None (utk count(WHERE …))
    where: Any | None         # AST cond, optional
    extra: list[Any] = None   # untuk ratio(num,denom) / delta(field, n)

    def __post_init__(self) -> None:
        if self.extra is None:
            self.extra = []


# ---------------------------------------------------------------------------
# Recursive descent parser — Metric expression
# ---------------------------------------------------------------------------
#
# Grammar (simplified):
#   expr      := term (('+' | '-') term)*
#   term      := factor (('*' | '/') factor)*
#   factor    := NUMBER | fn_call | field_ref | '(' expr ')' | UnaryMinus factor
#   fn_call   := KW '(' [field_ref | expr] ['WHERE' cond] (',' expr)* ')'
#   field_ref := IDENT (dotted)
#   cond      := or_expr
#   or_expr   := and_expr ('OR' and_expr)*
#   and_expr  := not_expr ('AND' not_expr)*
#   not_expr  := 'NOT' not_expr | cmp
#   cmp       := atom (CMPOP atom)?
#   atom      := NUMBER | STRING | BOOL | NULL | field_ref | '(' cond ')'

_CMP_OPS = {"==", "!=", ">=", "<=", ">", "<"}
_KW_FN = {"sum", "avg", "count", "ratio", "max", "min", "delta"}


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.i = 0

    # ------ utilities ------
    def peek(self, offset: int = 0) -> Token | None:
        idx = self.i + offset
        return self.tokens[idx] if idx < len(self.tokens) else None

    def eat(self, type_: str | None = None, value: str | None = None) -> Token:
        t = self.peek()
        if t is None:
            raise DSLError(f"unexpected EOF (mengharapkan {type_ or value!r})")
        if type_ is not None and t.type != type_:
            raise DSLError(f"expected {type_} pada pos {t.pos}, dapat {t.type!r} value={t.value!r}")
        if value is not None and t.value != value:
            raise DSLError(f"expected {value!r} pada pos {t.pos}, dapat {t.value!r}")
        self.i += 1
        return t

    # ------ entry: expr (metric) ------
    def parse_expr(self) -> Any:
        node = self.parse_term()
        while True:
            t = self.peek()
            if t and t.type == "OP" and t.value in ("+", "-"):
                self.i += 1
                rhs = self.parse_term()
                node = BinOp(t.value, node, rhs)
            else:
                break
        return node

    def parse_term(self) -> Any:
        node = self.parse_factor()
        while True:
            t = self.peek()
            if t and t.type == "OP" and t.value in ("*", "/"):
                self.i += 1
                rhs = self.parse_factor()
                node = BinOp(t.value, node, rhs)
            else:
                break
        return node

    def parse_factor(self) -> Any:
        t = self.peek()
        if t is None:
            raise DSLError("unexpected EOF di factor")

        if t.type == "OP" and t.value == "-":
            self.i += 1
            return UnaryOp("-", self.parse_factor())
        if t.type == "NUMBER":
            self.i += 1
            return Num(float(t.value))
        if t.type == "OP" and t.value == "(":
            self.i += 1
            node = self.parse_expr()
            self.eat("OP", ")")
            return node
        if t.type == "KW" and t.value in _KW_FN:
            return self.parse_fn_call()
        if t.type == "IDENT":
            return self.parse_field_ref()
        raise DSLError(f"factor tak dikenal pada pos {t.pos}: {t.type}/{t.value!r}")

    def parse_field_ref(self) -> FieldRef:
        t = self.eat("IDENT")
        return FieldRef(t.value.split("."))

    def parse_fn_call(self) -> FnCall:
        name_tok = self.eat("KW")
        name = name_tok.value
        if name not in _KW_FN:
            raise DSLError(f"{name!r} bukan function")
        self.eat("OP", "(")
        arg: Any | None = None
        where: Any | None = None
        extra: list[Any] = []

        # Special: count() / count(WHERE ...) — first token bisa WHERE
        t = self.peek()
        if t and t.type == "OP" and t.value == ")":
            self.i += 1
            return FnCall(name, None, None, [])
        if t and t.type == "KW" and t.value == "WHERE":
            self.i += 1
            where = self.parse_cond_or()
        else:
            # ambil 1 argumen (field atau expr utk ratio/delta)
            arg = self.parse_expr()
            # optional WHERE
            t = self.peek()
            if t and t.type == "KW" and t.value == "WHERE":
                self.i += 1
                where = self.parse_cond_or()
            # extra args setelah koma
            while True:
                t = self.peek()
                if t and t.type == "COMMA":
                    self.i += 1
                    extra.append(self.parse_expr())
                else:
                    break

        self.eat("OP", ")")
        return FnCall(name, arg, where, extra)

    # ------ entry: cond (threshold + WHERE) ------
    def parse_cond_or(self) -> Any:
        node = self.parse_cond_and()
        while True:
            t = self.peek()
            if t and t.type == "KW" and t.value == "OR":
                self.i += 1
                rhs = self.parse_cond_and()
                node = BinOp("OR", node, rhs)
            else:
                break
        return node

    def parse_cond_and(self) -> Any:
        node = self.parse_cond_not()
        while True:
            t = self.peek()
            if t and t.type == "KW" and t.value == "AND":
                self.i += 1
                rhs = self.parse_cond_not()
                node = BinOp("AND", node, rhs)
            else:
                break
        return node

    def parse_cond_not(self) -> Any:
        t = self.peek()
        if t and t.type == "KW" and t.value == "NOT":
            self.i += 1
            return UnaryOp("NOT", self.parse_cond_not())
        return self.parse_cmp()

    def parse_cmp(self) -> Any:
        left = self.parse_cmp_atom()
        t = self.peek()
        if t and t.type == "OP" and t.value in _CMP_OPS:
            op = t.value
            self.i += 1
            right = self.parse_cmp_atom()
            return BinOp(op, left, right)
        return left

    def parse_cmp_atom(self) -> Any:
        t = self.peek()
        if t is None:
            raise DSLError("unexpected EOF di cmp atom")
        if t.type == "NUMBER":
            self.i += 1
            return Num(float(t.value))
        if t.type == "STRING":
            self.i += 1
            return Str(t.value[1:-1])
        if t.type == "KW" and t.value in ("TRUE", "FALSE"):
            self.i += 1
            return Bool(t.value == "TRUE")
        if t.type == "KW" and t.value in ("None", "NULL"):
            self.i += 1
            return Null()
        if t.type == "OP" and t.value == "(":
            self.i += 1
            node = self.parse_cond_or()
            self.eat("OP", ")")
            return node
        if t.type == "IDENT":
            return self.parse_field_ref()
        if t.type == "OP" and t.value == "-":
            self.i += 1
            inner = self.parse_cmp_atom()
            return UnaryOp("-", inner)
        raise DSLError(f"cmp atom tak dikenal pada pos {t.pos}: {t.type}/{t.value!r}")


def parse_metric_expression(text: str) -> Any:
    """Parse string expression → AST tree (for evaluator)."""
    tokens = tokenize(text)
    p = _Parser(tokens)
    node = p.parse_expr()
    if p.i != len(tokens):
        leftover = tokens[p.i]
        raise DSLError(f"token sisa setelah parse: {leftover}")
    return node


def parse_threshold_expression(text: str) -> Any:
    """Parse threshold condition (mis. '>=60 AND <80').

    Karena auditor sering tulis singkat ('>=60' tanpa LHS), kita inject
    `value` sbg LHS implisit untuk operator perbandingan paling depan.
    """
    s = text.strip()
    # Inject 'value' bila expression mulai dengan operator perbandingan
    if s and (s.startswith(">") or s.startswith("<") or s.startswith("==") or s.startswith("!=")):
        s = "value " + s
    # Inject `value` di setiap awal sub-expression setelah AND/OR/NOT diikuti operator
    # (mis. '>=40 AND <60' → 'value >=40 AND value <60')
    # Implementasi sederhana: regex replace token-level.
    s = re.sub(r"(?:^|\b(AND|OR|NOT)\s+)(?=[<>=!])", lambda m: (m.group(0) + "value "), s)
    # Karena lookbehind+lookahead di atas pakai pola yg menelan group, fallback:
    # cek apakah hasilnya valid; kalau gagal, retry dgn cara lain.
    try:
        tokens = tokenize(s)
    except DSLError:
        # last resort: inject `value` sebelum tiap >/</== yg dahului oleh KW
        s2 = re.sub(r"(AND|OR|NOT)\s*([<>=!])", r"\1 value \2", text.strip())
        tokens = tokenize(s2)
    p = _Parser(tokens)
    node = p.parse_cond_or()
    if p.i != len(tokens):
        leftover = tokens[p.i]
        raise DSLError(f"token sisa setelah threshold: {leftover}")
    return node


# ---------------------------------------------------------------------------
# Evaluator interpreter
# ---------------------------------------------------------------------------
#
# Konteks evaluasi:
#   - rows: list[dict] (CacmObservasi.data list)
#   - vars: dict (mis. {'value': hasil metric}) saat eval threshold
#
# Field reference `data.x` mengakses `row['data']['x']`. Convention v7:
# CacmObservasi.data adalah JSONB column, accessed via row dict.

def _resolve_field(row: dict, path: list[str]) -> Any:
    """Resolve dotted path di row. None bila path tidak ada."""
    cur: Any = row
    for k in path:
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(k)
        else:
            return None
    return cur


def _eval_cond(node: Any, row: dict, env: dict) -> bool:
    """Eval boolean expression atas 1 row + env (utk WHERE clause)."""
    if isinstance(node, BinOp):
        if node.op == "AND":
            return _eval_cond(node.left, row, env) and _eval_cond(node.right, row, env)
        if node.op == "OR":
            return _eval_cond(node.left, row, env) or _eval_cond(node.right, row, env)
        if node.op in _CMP_OPS:
            left = _eval_atom(node.left, row, env)
            right = _eval_atom(node.right, row, env)
            return _apply_cmp(node.op, left, right)
        raise DSLError(f"binop tak dikenal: {node.op}")
    if isinstance(node, UnaryOp):
        if node.op == "NOT":
            return not _eval_cond(node.operand, row, env)
        raise DSLError(f"unary op tak dikenal: {node.op}")
    # bare atom — interpret sbg boolean (truthy)
    v = _eval_atom(node, row, env)
    return bool(v)


def _eval_atom(node: Any, row: dict, env: dict) -> Any:
    if isinstance(node, Num):
        return node.val
    if isinstance(node, Str):
        return node.val
    if isinstance(node, Bool):
        return node.val
    if isinstance(node, Null):
        return None
    if isinstance(node, FieldRef):
        # Convention: `value` adalah env var hasil metric (utk threshold)
        if node.path == ["value"]:
            return env.get("value")
        return _resolve_field(row, node.path)
    if isinstance(node, BinOp):
        if node.op in _CMP_OPS:
            return _apply_cmp(node.op, _eval_atom(node.left, row, env), _eval_atom(node.right, row, env))
        if node.op in ("AND", "OR"):
            return _eval_cond(node, row, env)
        return _apply_arith(node.op, _eval_atom(node.left, row, env), _eval_atom(node.right, row, env))
    if isinstance(node, UnaryOp):
        if node.op == "-":
            v = _eval_atom(node.operand, row, env)
            return -float(v) if v is not None else None
        if node.op == "NOT":
            return not _eval_cond(node.operand, row, env)
    if isinstance(node, FnCall):
        # fn calls hanya valid di metric eval, bukan di threshold eval
        raise DSLError("function call tidak diizinkan di threshold expression")
    raise DSLError(f"atom tak dikenal: {type(node).__name__}")


def _apply_cmp(op: str, a: Any, b: Any) -> bool:
    """Comparison dgn null-safe coercion."""
    if a is None or b is None:
        if op == "==":
            return a is None and b is None
        if op == "!=":
            return not (a is None and b is None)
        return False
    # Numeric coercion bila kedua sisi angka-ish
    try:
        af = float(a); bf = float(b)
        return {
            "==": af == bf, "!=": af != bf,
            ">=": af >= bf, "<=": af <= bf,
            ">": af > bf, "<": af < bf,
        }[op]
    except (TypeError, ValueError):
        pass
    sa, sb = str(a), str(b)
    return {
        "==": sa == sb, "!=": sa != sb,
        ">=": sa >= sb, "<=": sa <= sb,
        ">": sa > sb, "<": sa < sb,
    }[op]


def _apply_arith(op: str, a: Any, b: Any) -> float:
    af = float(a) if a is not None else 0.0
    bf = float(b) if b is not None else 0.0
    if op == "+":
        return af + bf
    if op == "-":
        return af - bf
    if op == "*":
        return af * bf
    if op == "/":
        if bf == 0:
            return float("nan")
        return af / bf
    raise DSLError(f"arith op tak dikenal: {op}")


def _eval_fn(node: FnCall, rows: list[dict]) -> Any:
    """Eval function call atas list rows."""
    name = node.name
    if name == "count":
        if node.arg is None and node.where is None:
            return float(len(rows))
        n = 0
        for r in rows:
            if node.where is None or _eval_cond(node.where, r, {}):
                n += 1
        return float(n)
    if name in ("sum", "avg", "max", "min"):
        if not isinstance(node.arg, FieldRef):
            # Allow ratio/expressions inside? Fase 1: cukup field ref.
            raise DSLError(f"{name}() butuh field ref sebagai argumen")
        vals: list[float] = []
        for r in rows:
            if node.where is not None and not _eval_cond(node.where, r, {}):
                continue
            v = _resolve_field(r, node.arg.path)
            if v is None:
                continue
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                continue
        if not vals:
            return 0.0 if name == "sum" else None
        if name == "sum":
            return sum(vals)
        if name == "avg":
            return sum(vals) / len(vals)
        if name == "max":
            return max(vals)
        if name == "min":
            return min(vals)
    if name == "ratio":
        if not (isinstance(node.arg, FnCall) or hasattr(node.arg, "op")) and not node.extra:
            raise DSLError("ratio(numerator, denominator) butuh 2 argumen")
        num = eval_metric(node.arg, rows)
        if not node.extra:
            raise DSLError("ratio() butuh argumen kedua sebagai denominator")
        denom = eval_metric(node.extra[0], rows)
        if denom in (0, 0.0, None):
            return float("nan")
        return float(num) / float(denom)
    if name == "delta":
        # delta(metric, -1) — periode sebelumnya. Fase 1 placeholder.
        raise DSLError("delta() belum diimplementasi di Fase 1 (butuh history observasi)")
    raise DSLError(f"function tak dikenal: {name}")


def eval_metric(node: Any, rows: list[dict]) -> Any:
    """Eval AST metric expression atas list of rows. Return numeric/None."""
    if isinstance(node, Num):
        return node.val
    if isinstance(node, FieldRef):
        # bare field reference di metric tidak biasa — tapi kalau dipakai,
        # interpret sbg agregat sum default (jarang dipakai).
        if rows:
            v = _resolve_field(rows[0], node.path)
            try:
                return float(v) if v is not None else 0.0
            except (TypeError, ValueError):
                return 0.0
        return 0.0
    if isinstance(node, BinOp):
        if node.op in _CMP_OPS:
            return bool(_apply_cmp(node.op, eval_metric(node.left, rows), eval_metric(node.right, rows)))
        left = eval_metric(node.left, rows)
        right = eval_metric(node.right, rows)
        return _apply_arith(node.op, left, right)
    if isinstance(node, UnaryOp):
        if node.op == "-":
            v = eval_metric(node.operand, rows)
            return -float(v) if v is not None else None
    if isinstance(node, FnCall):
        return _eval_fn(node, rows)
    raise DSLError(f"node tak dikenal di metric: {type(node).__name__}")


def eval_threshold(node: Any, value: Any) -> bool:
    """Eval threshold condition. `value` di-bind ke variabel `value` di env."""
    env = {"value": value}
    return _eval_cond(node, {}, env)
