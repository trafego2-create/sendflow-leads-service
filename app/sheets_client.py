import json

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from app.config import settings

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_creds = Credentials.from_service_account_info(
    json.loads(settings.google_service_account_json), scopes=_SCOPES
)
_service = build("sheets", "v4", credentials=_creds)
_sheet_id = settings.google_sheet_id
_sheet_name = settings.google_sheet_name


def _col_letter(n: int) -> str:
    letters = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _get_headers() -> list[str]:
    result = (
        _service.spreadsheets()
        .values()
        .get(spreadsheetId=_sheet_id, range=f"'{_sheet_name}'!1:1")
        .execute()
    )
    return result.get("values", [[]])[0]


def find_row_index(match_column: str, match_value: str) -> int | None:
    headers = _get_headers()
    if match_column not in headers:
        raise ValueError(f"Coluna '{match_column}' não existe na planilha")
    col_letter = _col_letter(headers.index(match_column) + 1)
    result = (
        _service.spreadsheets()
        .values()
        .get(spreadsheetId=_sheet_id, range=f"'{_sheet_name}'!{col_letter}2:{col_letter}")
        .execute()
    )
    values = result.get("values", [])
    for i, row in enumerate(values):
        if row and str(row[0]) == str(match_value):
            return i + 2  # +1 pelo header, +1 porque é 1-based
    return None


def update_row(row_index: int, values: dict) -> None:
    headers = _get_headers()
    data = []
    for key, val in values.items():
        if key not in headers:
            continue
        col_letter = _col_letter(headers.index(key) + 1)
        data.append({"range": f"'{_sheet_name}'!{col_letter}{row_index}", "values": [[val]]})
    if not data:
        return
    body = {"valueInputOption": "USER_ENTERED", "data": data}
    _service.spreadsheets().values().batchUpdate(spreadsheetId=_sheet_id, body=body).execute()


def _next_row_index(match_column: str) -> int:
    headers = _get_headers()
    col_letter = _col_letter(headers.index(match_column) + 1)
    result = (
        _service.spreadsheets()
        .values()
        .get(spreadsheetId=_sheet_id, range=f"'{_sheet_name}'!{col_letter}2:{col_letter}")
        .execute()
    )
    return len(result.get("values", [])) + 2  # +1 pelo header, +1 porque é 1-based


def append_row(values: dict, match_column: str) -> None:
    # Escreve só nas células de 'values' (via update_row), na próxima linha vazia
    # de match_column. Não usa a API de append com INSERT_ROWS: isso insere uma
    # linha de verdade na planilha, empurrando pra baixo qualquer conteúdo que já
    # estivesse na linha seguinte (ex: fórmulas manuais como o "TOTAL LIMPO"),
    # deslocando o bloco de totais um pouco mais a cada dia.
    update_row(_next_row_index(match_column), values)


def upsert_row(match_column: str, match_value: str, values: dict) -> None:
    row_index = find_row_index(match_column, match_value)
    if row_index:
        update_row(row_index, values)
    else:
        full_values = {match_column: match_value, **values}
        append_row(full_values, match_column)


def increment_cell(match_column: str, match_value: str, field: str, delta: int = 1) -> None:
    """Soma delta ao valor atual de field na linha onde match_column == match_value,
    criando a linha se não existir ainda."""
    headers = _get_headers()
    row_index = find_row_index(match_column, match_value)
    if row_index:
        col_letter = _col_letter(headers.index(field) + 1)
        current = (
            _service.spreadsheets()
            .values()
            .get(spreadsheetId=_sheet_id, range=f"'{_sheet_name}'!{col_letter}{row_index}")
            .execute()
            .get("values", [])
        )
        atual = int(current[0][0]) if current and current[0] and current[0][0] else 0
        update_row(row_index, {field: atual + delta})
    else:
        append_row({match_column: match_value, field: delta}, match_column)


def update_summary_row(values: dict) -> None:
    """Atualiza a linha fixa de totais (linha 2 da planilha, equivalente ao row_number=2 do n8n)."""
    update_row(2, values)
