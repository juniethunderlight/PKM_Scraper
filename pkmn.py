#!/usr/bin/env python3
"""
pkmn.py — Gestor de Pokédex y Movimientos para TTRPG
Uso:
  python pkmn.py addmove   <nombre_movimiento>
  python pkmn.py addpkm    <nombre_pokemon> [nivel]
  python pkmn.py updatepkm <nombre_pokemon> [nivel]
  python pkmn.py hidepkm   <nombre_pokemon>
  python pkmn.py showpkm   <nombre_pokemon>
  python pkmn.py orderby
"""

import sys
import math
import re

import gspread
from google.oauth2.service_account import Credentials

import scraper as sc

if not sys.stdout.encoding or "utf" not in sys.stdout.encoding.lower():
    sys.stdout.reconfigure(encoding="utf-8")

# ── Configuración ──────────────────────────────────────────────────────────────
SPREADSHEET_ID   = "1AuH-vO9V54eRdXBVyjVPCbtuwuk6JeQNuEOdFSRAU3g"
CREDENTIALS_FILE = "credentials.json"
MOVES_SHEET      = "MOVIMIENTOS"

# ── Posiciones de celdas en la ficha del Pokémon ───────────────────────────────
# Actualiza estas celdas si no coinciden con tu plantilla.
CELL_SEXO       = "D3"   # Sexo (ratio macho/hembra)
CELL_HABILIDAD  = "F6"   # Habilidad
CELL_OBJETO     = "F9"   # Objeto
CELL_NATURA     = "A26"  # Naturaleza (nombre - genética)
CELL_GENETICA   = "A27"  # Genética (sin uso; reservado)
CELL_LE_GUSTA   = "B23"  # Le gusta
CELL_NO_LE_GUSTA= "B24"  # No le gusta
CELL_RESISTE    = "C7"   # Resiste a...
CELL_DEBIL      = "C10"  # Débil a...
CELL_NOTAS     = "G20"   # Primer párrafo de la zona Notas (G20:H27 merged)
MOVE_START_ROW = 14      # Primera fila de movimientos en la ficha (tabla filas 14-17)


# ── Google Sheets ──────────────────────────────────────────────────────────────

def get_spreadsheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds  = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    gc     = gspread.authorize(creds)
    return gc.open_by_key(SPREADSHEET_ID)


# ── Utilidades de hojas ────────────────────────────────────────────────────────

def _find_sheet(sheets, name):
    """Busca la pestaña por nombre exacto; si no, insensible a mayúsculas/espacios."""
    if name in sheets:
        return sheets[name], name
    key = name.strip().lower()
    for title, ws in sheets.items():
        if title.strip().lower() == key:
            return ws, title
    return None, None


# ── Hoja Movimientos ───────────────────────────────────────────────────────────

# Tamaños de fuente por columna A-F en MOVIMIENTOS (no tocar backgroundColor)
_MOV_FONT_SIZES = [12, 12, 13, 14, 14, 11]


def _moves_worksheet(ss):
    """Devuelve la hoja de movimientos usando lookup flexible."""
    sheets = {ws.title: ws for ws in ss.worksheets()}
    ws, _ = _find_sheet(sheets, MOVES_SHEET)
    if ws is None:
        raise Exception(f"No se encontró la hoja '{MOVES_SHEET}'. Hojas disponibles: {list(sheets)}")
    return ws


def _existing_moves(ss):
    """Devuelve set de nombres de movimientos ya en la hoja (columna C, lowercase)."""
    col = _moves_worksheet(ss).col_values(3)
    return {v.strip().lower() for v in col if v.strip()}


def _move_row(name):
    """Scrapes a move and returns the 6-column row for both sheets."""
    m = sc.scrape_move(name)
    tipo_col = f"{m['tipo']} | {m['categoria']}"
    potencia = sc.power_to_dice(m["potencia"]) if m["potencia"] != "-" else "-"
    return [m["atributo"], tipo_col, name, potencia, m["precision"], m["efecto"]]


def _format_movimientos_row(ss, ws, row_1indexed):
    """Aplica formato de texto y bordes a una fila recién añadida en MOVIMIENTOS.
    No toca backgroundColor para respetar los colores de chips que el usuario haya definido."""
    sid   = ws.id
    row_0 = row_1indexed - 1
    border  = {"style": "SOLID", "width": 1, "color": {}}
    borders = {k: border for k in ("top", "bottom", "left", "right")}
    requests = [
        {"repeatCell": {
            "range": {
                "sheetId": sid,
                "startRowIndex": row_0, "endRowIndex": row_0 + 1,
                "startColumnIndex": col, "endColumnIndex": col + 1,
            },
            "cell": {"userEnteredFormat": {
                "textFormat": {"bold": True, "fontSize": sz},
                "borders": borders,
            }},
            "fields": "userEnteredFormat.textFormat.bold,"
                      "userEnteredFormat.textFormat.fontSize,"
                      "userEnteredFormat.borders",
        }}
        for col, sz in enumerate(_MOV_FONT_SIZES)
    ]
    ss.batch_update({"requests": requests})


def _append_to_movimientos(ss, row_data):
    """Añade una fila a MOVIMIENTOS y le aplica el formato estándar."""
    ws   = _moves_worksheet(ss)
    resp = ws.append_row(row_data, value_input_option="USER_ENTERED")
    m    = re.search(r"!A(\d+)", resp.get("updates", {}).get("updatedRange", ""))
    if m:
        _format_movimientos_row(ss, ws, int(m.group(1)))


def _add_move_to_sheet(ss, name):
    print(f" Agregando movimiento '{name}' a Movimientos...")
    _append_to_movimientos(ss, _move_row(name))


def _write_moves_to_ficha(ws, selected, ss):
    """Write moves to the Pokémon sheet and add new ones to MOVIMIENTOS."""
    existing = _existing_moves(ss)
    for i, mv in enumerate(selected):
        try:
            row_data = _move_row(mv)
        except Exception as e:
            print(f" No se pudo scrapear '{mv}': {e}")
            row_data = ["-", "-", mv, "-", "-", "-"]

        if mv.lower() not in existing:
            print(f" Agregando movimiento '{mv}' a Movimientos...")
            _append_to_movimientos(ss, row_data)
            existing.add(mv.lower())

        row_num = MOVE_START_ROW + i
        ws.update(values=[row_data], range_name=f"A{row_num}:F{row_num}")

    print(f"  Movimientos: {', '.join(selected)}")


def addmove(name):
    print(f"\nBuscando movimiento '{name}' en Wikidex...")
    m = sc.scrape_move(name)

    tipo_col     = f"{m['tipo']} | {m['categoria']}"
    potencia_col = sc.power_to_dice(m["potencia"]) if m["potencia"] != "-" else "-"
    row = [m["atributo"], tipo_col, name, potencia_col, m["precision"], m["efecto"]]

    print(f"  Atributo : {m['atributo']}")
    print(f"  Tipo     : {tipo_col}")
    print(f"  Potencia : {potencia_col}")
    print(f"  Precisión: {m['precision']}")
    print(f"  Efecto   : {m['efecto']}")

    ss = get_spreadsheet()
    _moves_worksheet(ss).append_row(row, value_input_option="USER_ENTERED")
    print(f"\n '{name}' agregado a '{MOVES_SHEET}'.")


# ── Stats base ─────────────────────────────────────────────────────────────────

def _pokemon_stats(p):
    return {
        "ps":      math.ceil(p["hp"]  / 10),
        "atk":     math.ceil(p["atk"] / 10),
        "def_":    math.ceil(p["def"] / 10),
        "spa":     math.ceil(p["spa"] / 10),
        "spd":     math.ceil(p["spd"] / 10),
        "spe":     math.ceil(p["spe"] / 10),
        "tipos":   p["tipo"].replace(" | ", ", "),
        "num_fmt": f"#{int(p['numero']):04d}" if p["numero"] != "???" else "???",
    }


# ── Construcción de celdas de la ficha ─────────────────────────────────────────

def _ficha_cells(name, p, s, level=None, is_create=False):
    cells = []

    if p["img_url"]:
        cells.append({"range": "A1", "values": [[f'=IMAGE("{p["img_url"]}")']]})

    if is_create:
        cells.append({"range": "D1", "values": [[name]]})

    cells += [
        {"range": "D2",  "values": [[s["tipos"]]]},
        {"range": "B6",  "values": [[s["ps"]]]},
        {"range": "B7",  "values": [[s["atk"]]]},
        {"range": "B8",  "values": [[s["def_"]]]},
        {"range": "B9",  "values": [[s["spa"]]]},
        {"range": "B10", "values": [[s["spd"]]]},
        {"range": "B11", "values": [[s["spe"]]]},
        {"range": "C5",  "values": [["Salud (PS x NV /2)"]]},
        {"range": "B20", "values": [[p["nombre"]]]},
        {"range": "B21", "values": [[f'=HIPERVINCULO("https://www.wikidex.net/wiki/"&B20;"{s["num_fmt"]}")']]},
    ]

    if level is not None:
        cells += [
            {"range": "F1", "values": [["Nivel"]]},
            {"range": "G1", "values": [[level]]},
            {"range": "E5", "values": [["=B6*G1/2"]]},
            *([{"range": "D5", "values": [["=E5"]]}] if is_create else []),
        ]

    return cells


def _apply_ficha(ws, name, p, s, level, is_create=False):
    ws.batch_update(_ficha_cells(name, p, s, level, is_create=is_create),
                    value_input_option="USER_ENTERED")


# ── Datos aleatorios (solo al crear) ───────────────────────────────────────────

def _random_cells(soup, level, ss):
    """
    Returns batch_update-compatible list of cells with:
    ability, item, nature, genetics, resistances, weaknesses,
    Pokédex summary, and 4 random moves.
    Also adds new moves to the Movimientos sheet.
    """
    cells = []

    gender_str  = sc.scrape_gender(soup)

    abilities   = sc.scrape_abilities(soup)
    ability     = sc.random_ability(abilities) or "-"
    ability_desc = sc.scrape_ability_description(ability) if ability != "-" else ""
    ability_str  = f"{ability} - {ability_desc}" if ability_desc else ability

    items     = sc.scrape_held_items(soup)
    item      = sc.random_item(items)

    nature    = sc.random_nature()
    genetics  = sc.random_genetics(nature).rstrip(".")

    eff       = sc.scrape_type_effectiveness(soup)
    resiste_str = ", ".join(eff["resiste"]) if eff["resiste"] else "-"
    debil_str   = ", ".join(eff["debil"])   if eff["debil"]   else "-"

    desc = sc.scrape_pokedex_descriptions(soup)

    natura_str = f"{nature['nombre']} - {genetics}" if genetics else nature["nombre"]

    cells += [
        {"range": CELL_SEXO,        "values": [[gender_str]]},
        {"range": CELL_HABILIDAD,   "values": [[ability_str]]},
        {"range": CELL_OBJETO,      "values": [[item]]},
        {"range": CELL_NATURA,      "values": [[natura_str]]},
        {"range": CELL_LE_GUSTA,    "values": [[nature["le_gusta"]]]},
        {"range": CELL_NO_LE_GUSTA, "values": [[nature["no_le_gusta"]]]},
        {"range": CELL_RESISTE,     "values": [[resiste_str]]},
        {"range": CELL_DEBIL,       "values": [[debil_str]]},
    ]

    if desc:
        cells.append({"range": CELL_NOTAS, "values": [[desc]]})

    print(f"  Sexo      : {gender_str}")
    print(f"  Habilidad : {ability_str}")
    print(f"  Naturaleza: {natura_str}")
    print(f"  Le gusta  : {nature['le_gusta']}  |  No le gusta: {nature['no_le_gusta']}")
    print(f"  Objeto    : {item}")
    print(f"  Resiste   : {resiste_str}")
    print(f"  Débil a   : {debil_str}")

    return cells, soup, level   # moves written separately after sheet creation


# ── Rellenar movimientos si están vacíos ──────────────────────────────────────

def _is_real_move(v):
    v = v.strip()
    return len(v) >= 2 and not v.lstrip("-0").isdigit() and v not in ("0", "-", "—")


def _fill_moves_if_empty(ws, soup, level, ss):
    """Si los 4 huecos de movimiento están vacíos, asigna movimientos aleatorios BDSP."""
    name_cells = [f"C{MOVE_START_ROW + i}" for i in range(4)]
    ranges     = ws.batch_get(name_cells)
    current    = [(r[0][0] if r and r[0] else "") for r in ranges]

    if any(_is_real_move(v) for v in current):
        return  # ya tiene movimientos

    _assign_random_moves(ws, soup, level, ss)


def _assign_random_moves(ws, soup, level, ss):
    """Asigna 4 movimientos aleatorios BDSP (fuerza la escritura, sin comprobar si ya hay)."""
    import random
    level_moves, egg_moves = sc.scrape_moves_bdsp(soup, max_level=level)
    pool = list(dict.fromkeys(level_moves + egg_moves))
    if not pool:
        print(" No se encontraron movimientos BDSP disponibles.")
        return
    selected = pool[:4] if len(pool) <= 4 else random.sample(pool, 4)
    _write_moves_to_ficha(ws, selected, ss)


# ── Rellenar habilidad/objeto si están vacíos ─────────────────────────────────

_EMPTY_VALS = {"", "0", "-", "—", "no"}


def _fill_gender_if_empty(ws, soup):
    current = (ws.acell(CELL_SEXO).value or "").strip()
    if current.lower() not in _EMPTY_VALS:
        return
    gender_str = sc.scrape_gender(soup)
    if gender_str:
        ws.update_acell(CELL_SEXO, gender_str)
        print(f"  Sexo      : {gender_str}")


def _fill_ability_if_empty(ws, soup):
    """Si la celda de habilidad está vacía o es placeholder, asigna una aleatoria."""
    current = (ws.acell(CELL_HABILIDAD).value or "").strip()
    if current.lower() not in _EMPTY_VALS:
        return
    abilities = sc.scrape_abilities(soup)
    ability   = sc.random_ability(abilities)
    if ability:
        ws.update_acell(CELL_HABILIDAD, ability)
        print(f"  Habilidad : {ability}")


def _fill_item_if_empty(ws, soup):
    """Si la celda de objeto está vacía o es placeholder, calcula aleatoriamente."""
    current = (ws.acell(CELL_OBJETO).value or "").strip()
    if current.lower() not in _EMPTY_VALS:
        return
    items = sc.scrape_held_items(soup)
    item  = sc.random_item(items)
    ws.update_acell(CELL_OBJETO, item)
    print(f"  Objeto    : {item}")


# ── Corrección de plantilla antigua ────────────────────────────────────────────

def _fix_sheet_template(ss, ws):
    """Detecta y corrige fichas con la plantilla antigua (sin '/2' en C5)."""
    c5 = ws.acell("C5").value or ""
    if "/2" in c5:
        return
    sid = ws.id
    print("  Detectada ficha desactualizada → corrigiendo estructura...")
    ss.batch_update({"requests": [
        {"unmergeCells": {"range": {"sheetId": sid,
            "startRowIndex": 0, "endRowIndex": 1,
            "startColumnIndex": 3, "endColumnIndex": 8}}},
        {"mergeCells": {"mergeType": "MERGE_ALL", "range": {"sheetId": sid,
            "startRowIndex": 0, "endRowIndex": 1,
            "startColumnIndex": 3, "endColumnIndex": 5}}},
        {"mergeCells": {"mergeType": "MERGE_ALL", "range": {"sheetId": sid,
            "startRowIndex": 0, "endRowIndex": 1,
            "startColumnIndex": 6, "endColumnIndex": 8}}},
        {"unmergeCells": {"range": {"sheetId": sid,
            "startRowIndex": 18, "endRowIndex": 19,
            "startColumnIndex": 5, "endColumnIndex": 7}}},
        {"unmergeCells": {"range": {"sheetId": sid,
            "startRowIndex": 19, "endRowIndex": 27,
            "startColumnIndex": 5, "endColumnIndex": 7}}},
        {"unmergeCells": {"range": {"sheetId": sid,
            "startRowIndex": 19, "endRowIndex": 27,
            "startColumnIndex": 7, "endColumnIndex": 8}}},
        {"mergeCells": {"mergeType": "MERGE_ALL", "range": {"sheetId": sid,
            "startRowIndex": 18, "endRowIndex": 19,
            "startColumnIndex": 6, "endColumnIndex": 8}}},
        {"mergeCells": {"mergeType": "MERGE_ALL", "range": {"sheetId": sid,
            "startRowIndex": 19, "endRowIndex": 27,
            "startColumnIndex": 5, "endColumnIndex": 6}}},
        {"mergeCells": {"mergeType": "MERGE_ALL", "range": {"sheetId": sid,
            "startRowIndex": 19, "endRowIndex": 27,
            "startColumnIndex": 6, "endColumnIndex": 8}}},
        {"unmergeCells": {"range": {"sheetId": sid,
            "startRowIndex": 16, "endRowIndex": 17,
            "startColumnIndex": 11, "endColumnIndex": 13}}},
    ]})
    ws.batch_update([
        {"range": "F1",  "values": [["Nivel"]]},
        {"range": "C3",  "values": [["Sexo"]]},
        {"range": "C5",  "values": [["Salud (PS x NV /2)"]]},
        {"range": "F19", "values": [["Cintas / sellos"]]},
        {"range": "G19", "values": [["Notas"]]},
        {"range": "H19", "values": [[""]]},
    ], value_input_option="USER_ENTERED")
    d3 = ws.acell("D3").value or ""
    if d3.strip().upper() == "NO":
        ws.update_cell(3, 4, "")
    print("  Estructura corregida.")


def _unhide_sheet(ss, sheet_id):
    ss.batch_update({"requests": [{
        "updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "hidden": False},
            "fields": "hidden",
        }
    }]})


# ── Comandos principales ───────────────────────────────────────────────────────

def addpkm(name, level=None):
    print(f"\nBuscando Pokémon '{name}' en Wikidex...")
    soup, p = sc.scrape_pokemon(name)
    s = _pokemon_stats(p)

    nivel_str = f"  Nivel: {level}" if level is not None else ""
    print(f"  {s['num_fmt']} {p['nombre']}{nivel_str}")
    print(f"  Tipo : {s['tipos']}")
    print(f"  PS: {s['ps']}  ATK: {s['atk']}  DEF: {s['def_']}  A.SP: {s['spa']}  D.SP: {s['spd']}  VEL: {s['spe']}")

    ss     = get_spreadsheet()
    sheets = {ws.title: ws for ws in ss.worksheets()}
    existing_ws, existing_title = _find_sheet(sheets, name)

    if existing_ws:
        print("  Pestaña ya existe → actualizando stats...")
        _fix_sheet_template(ss, existing_ws)
        _apply_ficha(existing_ws, existing_title, p, s, level, is_create=False)
        _fill_gender_if_empty(existing_ws, soup)
        _fill_ability_if_empty(existing_ws, soup)
        _fill_item_if_empty(existing_ws, soup)
        _fill_moves_if_empty(existing_ws, soup, level, ss)
        print(f"\n Pestaña '{existing_title}' actualizada.")
    else:
        salvaje = ss.worksheet("SALVAJE")
        print(f"  Creando pestaña '{name}'...")
        new_ws = ss.duplicate_sheet(salvaje.id,
                                    insert_sheet_index=len(sheets),
                                    new_sheet_name=name)
        _unhide_sheet(ss, new_ws.id)
        _apply_ficha(new_ws, name, p, s, level, is_create=True)
        rand_cells, rand_soup, rand_level = _random_cells(soup, level, ss)
        if rand_cells:
            new_ws.batch_update(rand_cells, value_input_option="USER_ENTERED")
        _fill_moves_if_empty(new_ws, rand_soup, rand_level, ss)
        print(f"\n Pestaña '{name}' creada.")


def updatepkm(name, level=None):
    print(f"\nBuscando Pokémon '{name}' en Wikidex...")
    soup, p = sc.scrape_pokemon(name)
    s = _pokemon_stats(p)

    nivel_str = f"  Nivel: {level}" if level is not None else ""
    print(f"  {s['num_fmt']} {p['nombre']}{nivel_str}")
    print(f"  Tipo : {s['tipos']}")
    print(f"  PS: {s['ps']}  ATK: {s['atk']}  DEF: {s['def_']}  A.SP: {s['spa']}  D.SP: {s['spd']}  VEL: {s['spe']}")

    ss     = get_spreadsheet()
    sheets = {ws.title: ws for ws in ss.worksheets()}
    existing_ws, existing_title = _find_sheet(sheets, name)

    if not existing_ws:
        print(f"\n  No existe una pestaña llamada '{name}'. Usa addpkm para crearla.")
        return

    _fix_sheet_template(ss, existing_ws)
    _apply_ficha(existing_ws, existing_title, p, s, level, is_create=False)
    _fill_gender_if_empty(existing_ws, soup)
    _fill_ability_if_empty(existing_ws, soup)
    _fill_item_if_empty(existing_ws, soup)
    if level is not None:
        _assign_random_moves(existing_ws, soup, level, ss)
    else:
        _fill_moves_if_empty(existing_ws, soup, level, ss)
    print(f"\n Pestaña '{existing_title}' actualizada.")


def hidepkm(name):
    ss = get_spreadsheet()
    sheets = {ws.title: ws for ws in ss.worksheets()}
    ws, title = _find_sheet(sheets, name)
    if not ws:
        print(f"  No existe una pestaña llamada '{name}'.")
        return
    ss.batch_update({"requests": [{"updateSheetProperties": {
        "properties": {"sheetId": ws.id, "hidden": True},
        "fields": "hidden",
    }}]})
    print(f" Pestaña '{title}' ocultada.")


def showpkm(name):
    ss = get_spreadsheet()
    sheets = {ws.title: ws for ws in ss.worksheets()}
    ws, title = _find_sheet(sheets, name)
    if not ws:
        print(f"  No existe una pestaña llamada '{name}'.")
        return
    ss.batch_update({"requests": [{"updateSheetProperties": {
        "properties": {"sheetId": ws.id, "hidden": False},
        "fields": "hidden",
    }}]})
    print(f" Pestaña '{title}' mostrada.")


def orderby():
    """
    Ordena las pestañas del spreadsheet alfabéticamente.
    Las hojas en MAYÚSCULAS COMPLETAS se mantienen al frente, en su orden relativo.
    """
    ss         = get_spreadsheet()
    all_sheets = ss.worksheets()

    caps_sheets    = [ws for ws in all_sheets if ws.title == ws.title.upper()]
    regular_sheets = [ws for ws in all_sheets if ws.title != ws.title.upper()]
    regular_sheets.sort(key=lambda ws: ws.title.lower())

    new_order = caps_sheets + regular_sheets
    requests  = [
        {"updateSheetProperties": {
            "properties": {"sheetId": ws.id, "index": idx},
            "fields": "index",
        }}
        for idx, ws in enumerate(new_order)
    ]
    ss.batch_update({"requests": requests})
    print(" Pestañas ordenadas:")
    for ws in new_order:
        print(f"  {ws.title}")


# ── Entry point ────────────────────────────────────────────────────────────────

def parse_args(argv):
    if argv and argv[-1].isdigit():
        return " ".join(argv[:-1]), int(argv[-1])
    return " ".join(argv), None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "orderby":
        orderby()
        return

    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    name, level = parse_args(sys.argv[2:])

    if cmd == "addmove":
        addmove(name)
    elif cmd == "addpkm":
        addpkm(name, level)
    elif cmd == "updatepkm":
        updatepkm(name, level)
    elif cmd == "hidepkm":
        hidepkm(name)
    elif cmd == "showpkm":
        showpkm(name)
    else:
        print(f"Comando desconocido: '{cmd}'.")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
