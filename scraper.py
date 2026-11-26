"""
scraper.py — Funciones de scraping de Wikidex para pkmn.py
"""

import math
import re
import random
import json
import os
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PKMNTTRPGScript/1.0)"}

CONTEST_ABBR = {
    "belleza": "BE", "ingenio": "IN", "dureza": "DR",
    "carisma": "CR", "dulzura": "DL",
}

DICE_TIERS = [
    (25,  "1d2"), (35,  "1d4"), (49,  "1d6"),
    (79,  "1d8"), (119, "1d10"), (float("inf"), "1d20"),
]

STAT_LABELS = {
    "ps": "hp", "ataque": "atk", "defensa": "def",
    "at. esp.": "spa", "def. esp.": "spd", "velocidad": "spe",
}

_NATURES_DATA = None


def load_natures():
    global _NATURES_DATA
    if _NATURES_DATA is None:
        path = os.path.join(os.path.dirname(__file__), "data", "natures.json")
        with open(path, encoding="utf-8") as f:
            _NATURES_DATA = json.load(f)
    return _NATURES_DATA


# ── Utilidades ─────────────────────────────────────────────────────────────────

def power_to_dice(raw):
    m = re.search(r"\d+", str(raw))
    if not m:
        return "-"
    p = int(m.group())
    for ceiling, dice in DICE_TIERS:
        if p <= ceiling:
            return f"{p} ({dice})"


def wikidex_soup(name):
    url = f"https://www.wikidex.net/wiki/{quote(name, safe='')}"
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def tipo_from_link(tag):
    for a in tag.find_all("a"):
        title = a.get("title", "")
        if title.lower().startswith("tipo "):
            return title[5:].capitalize()
    return "-"


def thumb_to_full(src):
    return re.sub(r"/\d+px-[^/]+$", "", src.replace("/thumb/", "/"))


def _types_in_tag(tag):
    return [a["title"][5:].capitalize()
            for a in tag.find_all("a")
            if a.get("title", "").lower().startswith("tipo ")]


# ── Movimientos ────────────────────────────────────────────────────────────────

def scrape_move(name):
    soup = wikidex_soup(name)
    result = {
        "atributo": "-", "tipo": "-", "categoria": "-",
        "potencia": "-", "precision": "-", "efecto": "-",
    }

    for table in soup.find_all("table", class_="datos"):
        for row in table.find_all("tr"):
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            key = th.get_text(strip=True).lower()

            if key == "tipo":
                t = tipo_from_link(td)
                if t != "-":
                    result["tipo"] = t

            elif key == "clase":
                for a in td.find_all("a"):
                    title = a.get("title", "").lower()
                    if title.startswith("clase "):
                        cat = title[6:].strip()
                        # "de estado" → "Estado" (status moves)
                        if cat == "de estado":
                            cat = "estado"
                        result["categoria"] = cat.capitalize()
                        break

            elif key == "potencia":
                for sup in td.find_all("sup"):
                    sup.decompose()
                val = td.get_text(strip=True)
                result["potencia"] = val if val not in ("—", "-", "") else "-"

            elif key in ("precisión", "precision"):
                for sup in td.find_all("sup"):
                    sup.decompose()
                val = td.get_text(strip=True)
                result["precision"] = val if val not in ("—", "-", "") else "-"

            elif key == "cualidad" and result["atributo"] == "-":
                a_tag = td.find("a", title=True)
                img_tag = td.find("img", alt=True)
                val = (a_tag["title"] if a_tag else
                       img_tag["alt"] if img_tag else "").lower()
                if val:
                    result["atributo"] = CONTEST_ABBR.get(val, val[:2].upper())

            elif key == "efecto secundario" and result["efecto"] == "-":
                val = td.get_text(separator=" ", strip=True).replace("\xa0", " ")
                if val.lower() not in ("ninguno", "-", "—", ""):
                    result["efecto"] = val[:120]

    return result


# ── Pokémon básico ─────────────────────────────────────────────────────────────

def scrape_pokemon(name):
    soup = wikidex_soup(name)
    result = {
        "numero": "???", "nombre": name, "tipo": "-", "img_url": "",
        "hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0,
    }

    for a in soup.find_all("a"):
        txt = a.get_text(strip=True)
        if re.match(r"^#\d{3,4}$", txt):
            result["numero"] = str(int(txt.lstrip("#")))
            break

    datos = soup.find("table", class_="datos")
    if datos:
        for row in datos.find_all("tr"):
            th = row.find("th")
            td = row.find("td")
            if th and "tipo" in th.get_text(strip=True).lower() and td:
                tipos = [a["title"][5:].capitalize()
                         for a in td.find_all("a")
                         if a.get("title", "").lower().startswith("tipo ")]
                if tipos:
                    result["tipo"] = " | ".join(tipos)
                break

    carac = soup.find("table", class_="caracteristicas")
    if carac:
        for row in carac.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            stat = STAT_LABELS.get(cells[0].get_text(strip=True).lower())
            if stat:
                nums = re.findall(r"\d+", cells[1].get_text(strip=True))
                if nums:
                    result[stat] = int(nums[0])

    for img in soup.find_all("img"):
        alt = img.get("alt", "")
        src = img.get("src", "")
        if alt.startswith("Ilustración de") and "wikidex" in src:
            result["img_url"] = thumb_to_full(src)
            break

    return soup, result


# ── Sexo ───────────────────────────────────────────────────────────────────────

def scrape_gender(soup):
    """
    Returns gender ratio string.
    - Only one gender (100/0): '♂' or '♀'
    - Decimal ratio: rounds the higher value up and the lower down (e.g. '88% ♂ - 12% ♀')
    - Whole numbers: 'X% M - Y% ♀'
    - No gender: 'Sin sexo'
    """
    for table in soup.find_all("table", class_="datos"):
        for row in table.find_all("tr"):
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            if "sexo" not in th.get_text(strip=True).lower():
                continue
            text = td.get_text(separator="|", strip=True)
            if "sin sexo" in text.lower():
                return "Sin sexo"
            parts = [p.strip() for p in text.split("|") if p.strip()]
            nums = [p for p in parts if re.match(r"[\d,\.]+%?$", p)]
            if len(nums) >= 2:
                m_raw = nums[0].rstrip("%").replace(",", ".")
                f_raw = nums[1].rstrip("%").replace(",", ".")
                m_val = float(m_raw)
                f_val = float(f_raw)
                if m_val == 100:
                    return "♂"
                if f_val == 100:
                    return "♀"
                # Round decimals: higher value up, lower value down
                if m_val != int(m_val) or f_val != int(f_val):
                    if m_val > f_val:
                        m_str = str(math.ceil(m_val))
                        f_str = str(math.floor(f_val))
                    else:
                        m_str = str(math.floor(m_val))
                        f_str = str(math.ceil(f_val))
                else:
                    m_str = str(int(m_val))
                    f_str = str(int(f_val))
                return f"{m_str}% ♂ - {f_str}% ♀"
            break
    return ""


# ── Habilidades ────────────────────────────────────────────────────────────────

def scrape_abilities(soup):
    """Returns list of {'nombre': str, 'oculta': bool}."""
    abilities = []
    for table in soup.find_all("table", class_="datos"):
        for row in table.find_all("tr"):
            th = row.find("th")
            if not th or "habilidad" not in th.get_text(strip=True).lower():
                continue
            td = row.find("td")
            if not td:
                break

            td_html = str(td)
            td_text = td.get_text()

            # Look for hidden-ability markers: parentheses or superscript with "O"
            # wikidex marks hidden ability as "(Nombre)" at end or with <sup>(O)</sup>
            links = td.find_all("a", title=True)
            for a in links:
                ability_name = a.get_text(strip=True)
                if not ability_name:
                    continue
                # Determine hidden: check if preceded by "(" in td text
                idx = td_text.find(ability_name)
                before = td_text[:idx].rstrip()
                is_hidden = before.endswith("(")
                # Also check for <sup> containing "O" or "oculta" after link
                sib = a.find_next_sibling()
                if sib and re.search(r"oculta|^\(O\)$", sib.get_text(), re.I):
                    is_hidden = True
                abilities.append({"nombre": ability_name, "oculta": is_hidden})
            break

    return abilities


HIDDEN_ABILITY_CHANCE = 0.10   # 10 % de probabilidad de habilidad oculta

_GEN_PREFIX  = re.compile(r"^[^.]{0,60}generaci[oó]n\s*", re.IGNORECASE)
_ALT_NAMES   = re.compile(r"^[^./]{2,80}/\s*")   # "Mar de Llamas / "


def scrape_ability_description(name):
    """Fetches the ability page and returns a short combat-effect description."""
    try:
        soup = wikidex_soup(name)
    except Exception:
        return ""

    def _clean(text):
        text = text.replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text).strip()
        # Strip "X generación" prefix (handles "Tercera generación", "Desde X a Y generación", etc.)
        text = _GEN_PREFIX.sub("", text).strip()
        # Strip alternative name forms like "Mar de Llamas / Mar Llamas "
        text = _ALT_NAMES.sub("", text).strip()
        # Strip ability name from the start (case-insensitive)
        if text.lower().startswith(name.lower()):
            text = text[len(name):].lstrip(" -:/")
        text = text.capitalize()
        # Truncate at first sentence boundary within 120 chars
        if len(text) > 120:
            cut = text.rfind(".", 0, 120)
            text = (text[: cut + 1] if cut > 40 else text[:120]).strip()
        return text

    # 1. Look for "En combate" subheading first
    for tag in soup.find_all(["h2", "h3", "h4"]):
        if "en combate" in tag.get_text(strip=True).lower():
            for sib in tag.next_siblings:
                n = getattr(sib, "name", None)
                if n in ("h2", "h3", "h4"):
                    break
                if n in ("p", "dl") and hasattr(sib, "get_text"):
                    t = sib.get_text(separator=" ", strip=True)
                    if len(t) > 20:
                        return _clean(t)
            break

    # 2. Fallback: "Efecto" heading + first <p>
    for tag in soup.find_all(["h2", "h3"]):
        if tag.get_text(strip=True).lower().startswith("efecto"):
            for sib in tag.next_siblings:
                n = getattr(sib, "name", None)
                if n in ("h2", "h3"):
                    break
                if n == "p" and hasattr(sib, "get_text"):
                    t = sib.get_text(separator=" ", strip=True)
                    if len(t) > 20:
                        return _clean(t)
            break

    return ""


def random_ability(abilities):
    """
    Elige una habilidad aleatoria.
    La habilidad oculta solo aparece si la 'tirada' supera HIDDEN_ABILITY_CHANCE.
    """
    if not abilities:
        return None
    regulars = [a for a in abilities if not a["oculta"]]
    hiddens  = [a for a in abilities if a["oculta"]]
    if not regulars:
        return hiddens[0]["nombre"] if hiddens else None
    if hiddens and random.random() < HIDDEN_ABILITY_CHANCE:
        return random.choice(hiddens)["nombre"]
    return random.choice(regulars)["nombre"]


# ── Objeto ─────────────────────────────────────────────────────────────────────

def scrape_held_items(soup):
    """Returns list of item names the Pokémon can hold in the wild (may be empty)."""
    items = []
    for table in soup.find_all("table", class_="datos"):
        for row in table.find_all("tr"):
            th = row.find("th")
            if not th:
                continue
            key = th.get_text(strip=True).lower()
            if "objeto" not in key:
                continue
            td = row.find("td")
            if not td:
                break
            for a in td.find_all("a"):
                name = a.get_text(strip=True)
                if name and name.lower() not in ("—", "-", "ninguno", "no"):
                    items.append(name)
            break
    return items


def random_item(items):
    """Usually NO; if items listed, 50 % chance of having one."""
    if not items:
        return "NO"
    return random.choice(items) if random.random() < 0.5 else "NO"


# ── Debilidades / Resistencias ─────────────────────────────────────────────────

def scrape_type_effectiveness(soup):
    """
    Returns {'debil': [...], 'resiste': [...]}
    Encoding:
      debil  → UPPERCASE=4x (Superdébil), lowercase=2x (Débil)
      resiste→ UPPERCASE=0x (Inmune),     lowercase=0.5x/0.25x (Resistente/Superresistente)
    Only uses the first tabpokemon table (base form).
    """
    # Row-label → (category, case)
    LABEL_MAP = {
        "superdébil":      ("debil",   "UPPER"),
        "débil":           ("debil",   "lower"),
        "resistente":      ("resiste", "lower"),
        "superresistente": ("resiste", "lower"),
        "inmune":          ("resiste", "UPPER"),
    }

    debil   = []
    resiste = []
    seen    = set()

    deb_h = None
    for tag in soup.find_all(["h2", "h3"]):
        if "debilidades" in tag.get_text(strip=True).lower():
            deb_h = tag
            break

    search_root = soup
    if deb_h:
        # Collect siblings until the next h2
        candidates = []
        for sib in deb_h.next_siblings:
            if getattr(sib, "name", None) == "h2":
                break
            candidates.append(sib)
        from bs4 import BeautifulSoup as _BS, Tag
        search_root = _BS("".join(str(c) for c in candidates), "html.parser")

    table = search_root.find("table", class_="tabpokemon")
    if table is None:
        return {"debil": debil, "resiste": resiste}

    for row in table.find_all("tr"):
        row_text = row.get_text(separator=" ", strip=True).lower()
        cat, case = None, None
        for label, mapping in LABEL_MAP.items():
            if row_text.startswith(label):
                cat, case = mapping
                break
        if cat is None:
            continue

        for a in row.find_all("a"):
            title = a.get("title", "")
            if title.lower().startswith("tipo "):
                t = title[5:].capitalize()
                key = (t.lower(), cat)
                if key not in seen:
                    seen.add(key)
                    encoded = t.upper() if case == "UPPER" else t.capitalize()
                    (debil if cat == "debil" else resiste).append(encoded)

    return {"debil": debil, "resiste": resiste}


# ── Movimientos BDSP ───────────────────────────────────────────────────────────

def _extract_level_moves(table, max_lv):
    moves = []
    headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
    has_level_col = any("nv" in h or "nivel" in h or h.isdigit() for h in headers)
    if not has_level_col:
        return moves
    for row in table.find_all("tr")[1:]:
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        lvl_text = re.sub(r"\D", "", cells[0].get_text(strip=True))
        move_a = cells[1].find("a")
        move_name = move_a.get_text(strip=True) if move_a else cells[1].get_text(strip=True)
        if not move_name or len(move_name) < 2:
            continue
        try:
            lvl = int(lvl_text) if lvl_text else 1
            if max_lv is None or lvl <= max_lv:
                moves.append(move_name)
        except ValueError:
            pass
    return moves


def scrape_moves_bdsp(soup, max_level=None):
    """
    Returns (level_moves, egg_moves) — lists of move names.
    level_moves filtered to max_level if given.
    Only level-up and egg moves from BDSP; TM/HM, tutor, special excluded.
    """
    level_moves = []
    egg_moves   = []

    BDSP_PANEL_KW  = ("diamante brillante", "perla reluciente")
    BDSP_EGG_TITLE = "pokémon diamante brillante"

    # ── Level-up moves: fetch from lazy-loaded BDSP annex page ─────────────────
    for panel in soup.find_all("article"):
        title = (panel.get("title", "") or panel.get("data-title", "")).lower()
        if not any(k in title for k in BDSP_PANEL_KW):
            continue
        page_title = panel.get("data-tabber-page-title", "")
        if not page_title:
            # panel already loaded — parse tables directly
            for table in panel.find_all("table"):
                level_moves += _extract_level_moves(table, max_level)
        else:
            url = f"https://www.wikidex.net/wiki/{quote(page_title.replace(' ', '_'), safe=':/')}"
            try:
                r = requests.get(url, headers=HEADERS, timeout=15)
                r.raise_for_status()
                bdsp_soup = BeautifulSoup(r.text, "html.parser")
                for table in bdsp_soup.find_all("table"):
                    level_moves += _extract_level_moves(table, max_level)
            except Exception:
                pass
        break

    # ── Egg moves: all moves in the movhuevo table (move name is in column 1) ───
    egg_table = soup.find("table", class_="movhuevo")
    if egg_table:
        for row in egg_table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            move_a = cells[1].find("a")
            move_name = move_a.get_text(strip=True) if move_a else cells[1].get_text(strip=True)
            if move_name and len(move_name) >= 2:
                egg_moves.append(move_name)

    return level_moves, egg_moves


# ── Descripciones Pokédex ──────────────────────────────────────────────────────

_LANG_PREFIX = re.compile(r"^[A-Z]{2,3}\s*:\s*")
_MONTH_RE    = re.compile(
    r"\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto"
    r"|septiembre|octubre|noviembre|diciembre)\b", re.I
)


def scrape_pokedex_descriptions(soup):
    """
    Busca la sección 'Descripción Pokédex' y devuelve frases de juego únicas
    (máx. 450 caracteres). Descarta tablas de eventos y del anime.
    """
    seen      = set()
    sentences = []

    dex_heading = None
    for h in soup.find_all(["h2", "h3"]):
        if "descripción pokédex" in h.get_text(strip=True).lower():
            dex_heading = h
            break

    tables = []
    if dex_heading:
        for sib in dex_heading.next_siblings:
            tag = getattr(sib, "name", None)
            if tag == "h2":
                break
            if tag == "table":
                tables.append(sib)
    if not tables:
        tables = soup.find_all("table")

    for table in tables:
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            raw = cells[-1].get_text(separator=" ", strip=True)
            # Split on language-code markers ("ES :", "HA :", "JAP :", …)
            # so each language version is a separate fragment
            fragments = re.split(r"(?<!\w)[A-Z]{2,3}\s*:", raw)
            for text in fragments:
                text = text.strip()
                if len(text) < 25:
                    continue
                if _MONTH_RE.search(text):
                    continue
                words = text.split()
                if text.count(",") >= 3 and text.count(",") / max(len(words), 1) > 0.25:
                    continue

                for sent in re.split(r"(?<=[.!?])\s+", text):
                    sent = sent.strip()
                    if len(sent) < 20:
                        continue
                    norm = re.sub(r"\s+", " ", sent.lower())
                    if norm not in seen:
                        seen.add(norm)
                        sentences.append(sent)
                    if len(" ".join(sentences)) >= 400:
                        return " ".join(sentences)[:450]

    return " ".join(sentences)[:450]


# ── Naturaleza ─────────────────────────────────────────────────────────────────

def random_nature():
    """d100/4 ceiling → one of 25 natures."""
    natures = load_natures()["natures"]
    roll = random.randint(1, 100)
    idx  = math.ceil(roll / 4) - 1   # 0-indexed 0..24
    return natures[idx]


def random_genetics(nature):
    """Random personality phrase matching the nature's stat."""
    data   = load_natures()
    stat   = nature["stat"]
    phrases = data["genetics"].get(stat, [])
    return random.choice(phrases) if phrases else ""
