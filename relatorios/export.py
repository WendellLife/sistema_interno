"""Exportação CSV/XLSX/PDF de tabelas planas. Acima de LIMITE_SINCRONO vira job assíncrono."""

from __future__ import annotations

import csv
import io
import uuid
from decimal import Decimal
from typing import Any

from django.http import HttpResponse
from rest_framework import status
from rest_framework.response import Response

LIMITE_SINCRONO = 5000
FORMATOS = ("json", "csv", "xlsx", "pdf")


def _texto(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def csv_bytes(colunas: list[str], linhas: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=colunas, delimiter=";", extrasaction="ignore")
    w.writeheader()
    for linha in linhas:
        w.writerow({c: _texto(linha.get(c)) for c in colunas})
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def xlsx_bytes(colunas: list[str], linhas: list[dict], titulo: str = "Relatório") -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = titulo[:31]
    ws.append(colunas)
    for c in ws[1]:
        c.font = Font(bold=True)
    for linha in linhas:
        ws.append([_texto(linha.get(c)) for c in colunas])
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = max(12, min(48, max(len(str(c.value or "")) for c in col) + 2))
    ws.freeze_panes = "A2"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def pdf_bytes(colunas: list[str], linhas: list[dict], titulo: str = "Relatório") -> bytes:
    from django.utils.html import escape

    linhas_html = "".join(
        "<tr>" + "".join(f"<td>{escape(str(_texto(linha.get(c)) if linha.get(c) is not None else ''))}</td>" for c in colunas) + "</tr>"
        for linha in linhas
    )
    html = f"""<html><head><meta charset="utf-8"><style>
      @page {{ size: A4 landscape; margin: 14mm; }}
      body {{ font-family: sans-serif; font-size: 10px; color: #1f2933; }}
      h1 {{ font-size: 16px; margin: 0 0 8px; }}
      table {{ border-collapse: collapse; width: 100%; }}
      th, td {{ border: 1px solid #d9dee3; padding: 4px 6px; text-align: left; }}
      th {{ background: #eef2f5; }}
    </style></head><body><h1>{escape(titulo)}</h1>
    <table><thead><tr>{''.join(f'<th>{escape(c)}</th>' for c in colunas)}</tr></thead><tbody>{linhas_html}</tbody></table>
    </body></html>"""
    from weasyprint import HTML

    return HTML(string=html).write_pdf()


GERADORES = {"csv": (csv_bytes, "text/csv"),
             "xlsx": (xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
             "pdf": (pdf_bytes, "application/pdf")}  # fmt: skip


def gerar(formato: str, colunas: list[str], linhas: list[dict], titulo: str) -> tuple[bytes, str]:
    fn, mime = GERADORES[formato]
    dados = fn(colunas, linhas) if formato == "csv" else fn(colunas, linhas, titulo)
    return dados, mime


def responder(request, *, dados_json: dict, colunas: list[str], linhas: list[dict], nome: str):
    """`?formato=json|csv|xlsx|pdf`. Acima de LIMITE_SINCRONO: 202 {job_id} e o arquivo vai por e-mail."""
    formato = request.query_params.get("formato", "json")
    if formato not in FORMATOS:
        return Response({"formato": [f"Use um de: {', '.join(FORMATOS)}"]}, status=status.HTTP_400_BAD_REQUEST)
    if formato == "json":
        return Response(dados_json)
    if len(linhas) > LIMITE_SINCRONO:
        from .tasks import gerar_export

        job_id = str(uuid.uuid4())
        gerar_export.delay(job_id, request.user.pk, formato, colunas, [{c: _texto(linha.get(c)) for c in colunas} for linha in linhas], nome)
        return Response({"job_id": job_id, "linhas": len(linhas), "mensagem": "O arquivo será enviado por e-mail."},
                        status=status.HTTP_202_ACCEPTED)  # fmt: skip
    conteudo, mime = gerar(formato, colunas, linhas, nome)
    resp = HttpResponse(conteudo, content_type=mime)
    resp["Content-Disposition"] = f'attachment; filename="{nome}.{formato}"'
    return resp
