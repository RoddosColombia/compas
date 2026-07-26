#!/usr/bin/env python
"""Genera un PDF a partir de un documento markdown de contrato/spec (COMPAS).

Uso:
    python scripts/generate_contrato_pdf.py <doc.md> [salida.pdf]

Pensado para el contrato SISMO-V3 -> COMPAS (docs/CONTRATO-SISMO-V3-LOANTAPE.md):
lo entrega el CEO a quien prepara la exportación semanal de SISMO-V3. Renderiza
encabezados, párrafos, listas, bloques de código y TABLAS markdown (| a | b |).
"""

from __future__ import annotations

import sys
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

_NL = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}

_REPLACEMENTS = {
    "—": "-", "–": "-", "→": "->", "←": "<-", "≥": ">=", "≤": "<=",
    "•": "-", "·": "-", "…": "...", "“": '"', "”": '"', "‘": "'", "’": "'",
    "≡": "=", "×": "x", " ": " ", "|": "|",
}


def sanitize(s: str) -> str:
    for k, v in _REPLACEMENTS.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


def _fit(pdf: FPDF, text: str) -> str:
    epw = pdf.epw
    words: list[str] = []
    for word in text.split(" "):
        if not word or pdf.get_string_width(word) <= epw:
            words.append(word)
            continue
        cur = ""
        for ch in word:
            if pdf.get_string_width(cur + ch) > epw and cur:
                words.append(cur)
                cur = ch
            else:
                cur += ch
        if cur:
            words.append(cur)
    return " ".join(words)


class PDF(FPDF):
    def header(self) -> None:
        self.set_font("helvetica", "I", 8)
        self.set_text_color(120)
        self.cell(0, 6, "COMPAS - Contrato de datos SISMO-V3 -> COMPAS", align="R")
        self.ln(4)
        self.set_text_color(0)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("helvetica", "I", 7)
        self.set_text_color(150)
        self.cell(0, 6, f"Pag. {self.page_no()}", align="C")
        self.set_text_color(0)


def _is_table_row(line: str) -> bool:
    return line.lstrip().startswith("|") and line.rstrip().endswith("|")


def _is_table_sep(line: str) -> bool:
    body = line.strip().strip("|")
    return bool(body) and set(body) <= set("-: |")


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _write_table_row(pdf: PDF, cells: list[str], *, head: bool) -> None:
    pdf.set_font("helvetica", "B" if head else "", 8)
    pdf.set_fill_color(230) if head else pdf.set_fill_color(248)
    texto = "  |  ".join(cells)
    pdf.multi_cell(0, 4.5, _fit(pdf, texto), fill=True, border=0, **_NL)
    pdf.ln(0.5)


def _write_markdown(pdf: PDF, text: str) -> None:
    en_codigo = False
    for raw in text.splitlines():
        line = sanitize(raw.rstrip())
        if line.strip().startswith("```"):
            en_codigo = not en_codigo
            pdf.ln(1)
            continue
        if en_codigo:
            pdf.set_font("courier", "", 7)
            pdf.multi_cell(0, 4, _fit(pdf, line or " "), **_NL)
            continue
        if not line:
            pdf.ln(2.5)
            continue
        # fuera de código: limpiar marcadores inline de markdown (**negrita**, `código`)
        line = line.replace("**", "").replace("`", "")
        if _is_table_sep(line):
            continue
        if _is_table_row(line):
            _write_table_row(pdf, _cells(line), head=False)
            continue
        if line.startswith("### "):
            pdf.set_font("helvetica", "B", 11)
            pdf.multi_cell(0, 6, _fit(pdf, line[4:]), **_NL)
        elif line.startswith("## "):
            pdf.set_font("helvetica", "B", 13)
            pdf.ln(1)
            pdf.multi_cell(0, 7, _fit(pdf, line[3:]), **_NL)
        elif line.startswith("# "):
            pdf.set_font("helvetica", "B", 16)
            pdf.multi_cell(0, 9, _fit(pdf, line[2:]), **_NL)
        else:
            pdf.set_font("helvetica", "", 10)
            pdf.multi_cell(0, 5, _fit(pdf, line), **_NL)


def main() -> None:
    args = sys.argv[1:]
    if not args:
        sys.exit("Uso: python scripts/generate_contrato_pdf.py <doc.md> [salida.pdf]")
    md = Path(args[0]).resolve()
    if not md.exists():
        sys.exit(f"No existe: {md}")
    out = (
        Path(args[1]).resolve()
        if len(args) > 1
        else md.with_suffix(".pdf")
    )
    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    _write_markdown(pdf, md.read_text(encoding="utf-8"))
    pdf.output(str(out))
    print(f"PDF generado: {out}")


if __name__ == "__main__":
    main()
