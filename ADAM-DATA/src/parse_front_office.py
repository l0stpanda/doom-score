"""Parse cached Wikipedia wikitext into front-office spans.
Output rows: franchise_id, role, person, start_date, end_date, date_precision_start, date_precision_end,
in_season_start, interim, source_url, needs_verification.

Date rules (D28):
- day / month precision: as written (month-only -> last day of that month, i.e. never earlier than the truth).
- season precision (NHL coach pages, season links): start = Oct 1 of the season; if the predecessor's term ends
  in the same season it was an in-season change -> start = Jan 15 of the season's second calendar year.
- year precision (MLB pages, bare years / {{mlby}}): the change is placed AFTER that year's season and after the
  prediction moment: MLB -> Dec 31 of the year; NHL -> Jul 1 of the year (after the season ending that year +
  the June draft). Never inside season t.
"""
import json, os, re
from datetime import date
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIKI = os.path.join(ROOT, "data", "raw", "wikipedia")
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
DASH = r"\s*(?:–|—|-|&ndash;|&mdash;|\bto\b)\s*"  # \b: 'to' inside 'October' split terms before (fixed)


def wikitext(page):
    p = os.path.join(WIKI, page.replace("/", "_") + ".json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)["parse"]["wikitext"]


def url(page):
    return "https://en.wikipedia.org/wiki/" + page.replace(" ", "_")


# ---------------- wikitext cleaning ----------------
def strip_refs(s):
    s = re.sub(r"<ref[^>/]*/>", "", s)
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    return s


def season_years(s):
    """Season start years referenced as NHL season links or {{nhly|Y}} templates."""
    # NHL or team-season links; tolerate '_' for spaces and 'Season' capitalised ([[2009-10 NHL Season|2010]])
    ys = [int(y) for y in re.findall(r"\[\[(\d{4})[–-]\d{2,4}[ _][^|\]]*?season", s, flags=re.I)]
    ys += [int(y) for y in re.findall(r"\{\{(?:nhly|NHL Year)\|(\d{4})", s, flags=re.I)]
    return ys


def _sed(m):
    mo = list(MONTHS)
    a = f"{mo[int(m.group(2)) - 1].title()} {int(m.group(3))}, {m.group(1)}"
    b = f"{mo[int(m.group(5)) - 1].title()} {int(m.group(6))}, {m.group(4)}" if m.group(4) else "present"
    return f"{a} – {b}"


def clean(s):
    s = strip_refs(s)
    s = re.sub(r"\{\{sortname\|([^|}]+)\|([^|}]+)(?:\|[^}]*)?\}\}", r"\1 \2", s, flags=re.I)
    s = re.sub(r"\{\{(?:mlby|nhly|NHL Year)\|(\d{4})[^}]*\}\}", r"\1", s, flags=re.I)
    s = re.sub(r"\{\{start and end dates\|(\d{4})\|(\d{1,2})\|(\d{1,2})\|(?:(\d{4})\|(\d{1,2})\|(\d{1,2})|present)[^}]*\}\}",
               _sed, s, flags=re.I)
    s = re.sub(r"\{\{sort\|[^|}]*\|((?:[^{}]|\{\{[^{}]*\}\})*?)\}\}", r"\1", s, flags=re.I)
    s = re.sub(r"<sup>.*?</sup>|<small>|</small>|<br\s*/?>", " ", s, flags=re.S)
    s = re.sub(r"\{\{(?:dagger|ref label|nowrap)[^}]*\}\}", "", s, flags=re.I)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", s)
    s = re.sub(r"'''?|style=\"[^\"]*\"\s*\|?|align=\"?\w+\"?\s*\|?|scope=\"?\w+\"?\s*\|?|bgcolor=\S+", "", s)
    s = s.replace("&nbsp;", " ").replace("*", "")
    s = re.sub(r"[†‡§¤#^!]", "", s)
    return re.sub(r"\s+", " ", s).strip(" |!")


# ---------------- term parsing ----------------
DATE_RE = re.compile(r"(?:(\w+)\s+(\d{1,2}),?\s+(\d{4}))|(?:(\w+)\s+(\d{4}))|(\d{4})", re.I)


def parse_point(tok):
    """'June 20, 2005' -> (date, 'day'); 'July 1974' -> (date, 'month'); '2005' -> (2005, 'year')."""
    tok = tok.strip()
    if re.fullmatch(r"present|current|incumbent|", tok, flags=re.I):
        return None, "open"
    m = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", tok)
    if m and m.group(1).lower() in MONTHS:
        return date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2))), "day"
    m = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})", tok)
    if m and m.group(2).lower() in MONTHS:
        return date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1))), "day"
    m = re.fullmatch(r"([A-Za-z]+),?\s+(\d{4})", tok)
    if m and m.group(1).lower() in MONTHS:
        mo, y = MONTHS[m.group(1).lower()], int(m.group(2))
        nxt = date(y + (mo == 12), mo % 12 + 1, 1)
        return date.fromordinal(nxt.toordinal() - 1), "month"
    m = re.fullmatch(r"(\d{4})", tok)
    if m:
        return int(m.group(1)), "year"
    return "bad", "bad"


def parse_term(term):
    """Return (start, end) points from a cleaned term string, or None."""
    term = re.sub(r"\(.*?\)", "", term).strip(" ;,")
    parts = re.split(DASH, term, maxsplit=1)
    a = parse_point(parts[0])
    b = parse_point(parts[1]) if len(parts) > 1 else a  # single year/date = same start and end
    if a[1] in ("bad", "open") or b[1] == "bad":
        return None
    return a, b


def year_boundary(y, league):
    return date(y, 12, 31) if league == "MLB" else date(y, 7, 1)


# ---------------- table / bullet extraction ----------------
def sections(text):
    """Yield (heading, body); a sub-heading is prefixed with its parent ('General managers / Montreal Expos')."""
    parts = re.split(r"\n(=+)\s*([^=\n]+?)\s*\1", "\n" + text)
    yield "", parts[0]
    stack = []
    for i in range(1, len(parts) - 2, 3):
        lvl = len(parts[i])
        stack = [(l, h) for l, h in stack if l < lvl] + [(lvl, parts[i + 1].strip())]
        yield " / ".join(h for _, h in stack), parts[i + 2]


def table_rows(body):
    """Yield (cells, table_role): table_role comes from the table's column headers (e.g. Rangers:
    'President of Baseball Operations' table vs 'General manager' table under one section)."""
    for tbl in re.findall(r"\{\|.*?\n\|\}", body, flags=re.S):
        header = " ".join(clean(h) for h in re.findall(r'^!(?!scope="?row)(.*)$', tbl, flags=re.M)[:6])
        t_role = role_of(header) if role_of(header) in ("gm", "baseball_ops_president") else None
        for row in re.split(r"\n\|-[^\n]*", tbl)[1:]:
            raw = row.strip()
            if not raw or raw.startswith("|}"):
                continue
            cells = re.split(r"\n[|!]|\|\||!!", "\n" + raw)
            cells = [c for c in cells if c.strip() not in ("", "|}")]
            yield cells, t_role


def person_from(cell):
    raw = strip_refs(cell)
    if not re.search(r"\[\[|\{\{[Ss]ortname|\{\{[Ss]ort\||[A-Z][a-z]+ [A-Z]", raw):
        return None
    name = clean(raw)
    interim = bool(re.search(r"interim|acting", name, flags=re.I))
    name = re.sub(r"\s*\((?:interim|acting)[^)]*\)|\s*(?:interim|acting)\b", "", name, flags=re.I).strip(" ,*")
    if not name or re.search(r"\d", name) or len(name) > 40:
        return None
    return name, interim


def rows_from_tables(body):
    """Yield (person, interim, term_raw_cell) from wikitables: first person-looking cell + first term-looking cell."""
    for cells, t_role in table_rows(body):
        person, term = None, None
        for c in cells:
            if person is None and not re.fullmatch(r"\s*[\w\s=\"#:;]*\|?\s*\d{1,2}\s*", c):
                person = person_from(c)
                if person:
                    continue
            if person and term is None and (season_years(c) or re.search(r"\d{4}", clean(c))):
                term = c
                i = cells.index(c)
                nxt = clean(cells[i + 1]) if i + 1 < len(cells) else ""
                if not re.search(r"–|—|\d{4}\s*-|present", clean(c), flags=re.I) and not season_years(c) and \
                        (re.fullmatch(r"present|current|incumbent|[–—-]", nxt, flags=re.I) or parse_point(nxt)[1] in ("day", "month")):
                    term = clean(c) + " – " + ("present" if re.fullmatch(r"[–—-]|current|incumbent", nxt, flags=re.I) else nxt)
                break
        if person and term:
            row_role = next((role_of(clean(c)) for c in cells if role_of(clean(c)) in ("gm", "baseball_ops_president")
                             and len(clean(c)) < 60), None)
            yield person[0], person[1], term, row_role or t_role


RANGE = re.compile(r"((?:(?:%s)\s+)?\d{4})(?:\s*(?:–|—|-)\s*((?:(?:%s)\s+)?\d{4}|present|current))?" %
                   ("|".join(MONTHS), "|".join(MONTHS)), re.I)


def rows_from_bullets(body):
    """Bullets: '*[[Name]], Title 1998–2015; Title2 2015–present' or '*[[Name]] (title, 1992–1999)'."""
    for line in body.splitlines():
        if not line.lstrip().startswith("*"):
            continue
        txt = clean(line)
        m = re.match(r"([^,(]+?)\s*(?:,|\()\s*(.+)$", txt)
        if not m or re.search(r"\d", m.group(1)):
            continue
        person, rest, pos = m.group(1).strip(), m.group(2), 0
        for r in RANGE.finditer(rest):
            title = rest[pos:r.start()]
            pos = r.end()
            if int(re.search(r"\d{4}", r.group(1)).group()) > 2100:
                continue
            yield person, title, r.group(0)




def role_of(title):
    t = title.lower()
    if re.search(r"baseball operations|chief baseball officer|baseball ops", t) and "vice" not in t and "vp" not in t:
        return "baseball_ops_president"
    if "general manager" in t and "assistant" not in t:
        return "gm"
    if "head coach" in t or "coaches" in t:
        return "head_coach"
    return None


def spans_from_page(page, franchise_id, league, default_role):
    text = wikitext(page)
    if text is None:
        return []
    out = []
    for heading, body in sections(text):
        sec_role = role_of(heading) if league == "MLB" else default_role
        if league == "MLB" and sec_role is None and not re.search(r"executive|team", heading, flags=re.I):
            continue
        mlb_titles = league == "MLB" and re.search(r"president|executive", heading, flags=re.I)
        for person, interim, term, row_role in (rows_from_tables(body) if (sec_role or mlb_titles) else []):
            role = (row_role or sec_role) if league == "MLB" else sec_role
            if role:
                out.append(dict(franchise_id=franchise_id, role=role, person=person, interim=interim,
                                term_raw=term, page=page, row_idx=len(out)))
        if league == "NHL" and role_of(heading.split(" / ")[-1]) == default_role:
            # e.g. Utah main article: '* [[Andre Tourigny]], 2024–present' under 'Head coaches'
            for person, title, term in rows_from_bullets(body):
                out.append(dict(franchise_id=franchise_id, role=default_role, person=person,
                                interim=bool(re.search(r"interim|acting", title, flags=re.I)),
                                term_raw=term, page=page, row_idx=len(out)))
        if league == "MLB":
            for person, title, term in rows_from_bullets(body):
                own = role_of(title)
                r = own or (sec_role if not re.search(r"owner|president|director|scout|assistant|vice|chair", title, re.I) else None)
                if r in ("gm", "baseball_ops_president"):
                    out.append(dict(franchise_id=franchise_id, role=r, person=person,
                                    interim=bool(re.search(r"interim|acting", title, flags=re.I)),
                                    term_raw=term, page=page, row_idx=len(out)))
    return out


def resolve_dates(rows, league):
    """Turn term_raw into dates following the module docstring rules."""
    res = []
    for r in rows:
        ys = season_years(r["term_raw"])
        if r["role"] == "head_coach" and ys:
            e = None if re.search(r"present", r["term_raw"], re.I) else max(ys)
            # mixed form '[[2008–09 ... season|2008]]–2010': a plain end year Y = the season ending in Y
            tail = re.split(r"\]\]\s*(?:–|—|-|to)\s*", strip_refs(r["term_raw"]), maxsplit=1)
            if e is not None and len(tail) > 1 and not season_years(tail[1]):
                m = re.match(r"\s*(\d{4})\b", tail[1])
                if m:
                    e = max(e, int(m.group(1)) - 1)
            r.update(s_season=min(ys), e_season=e, prec="season")
            res.append(r)
            continue
        t = parse_term(clean(r["term_raw"]))
        if not t:
            continue
        (a, pa), (b, pb) = t
        r["start_date"] = year_boundary(a, league) if pa == "year" else a
        r["end_date"] = None if pb == "open" else (year_boundary(b, league) if pb == "year" else b)
        r["date_precision_start"], r["date_precision_end"] = pa, pb
        if r["role"] == "head_coach":  # dated coach rows -> NHL seasons (season t = Oct t .. Apr t+1)
            sd, ed = r["start_date"], r["end_date"]
            # regular season ~Oct 1 - Apr 10: a hire after ~Apr 10 is for the next season (e.g. Vigneault 2019-04-15)
            offseason_april = sd.month == 4 and sd.day > 10
            r["s_season"] = sd.year if (sd.month >= 5 or offseason_april) else sd.year - 1
            r["in_season_start"] = (sd.month in (11, 12, 1, 2, 3) or (sd.month == 4 and not offseason_april)
                                    or (sd.month == 10 and sd.day > 15))
            r["e_season"] = None if ed is None else (ed.year if ed.month >= 10 else ed.year - 1)
            if r["e_season"] is not None and r["e_season"] < r["s_season"]:
                continue  # zero-length (e.g. interim between seasons)
        res.append(r)
    # season-precision coaches -> dates; detect in-season changes from overlapping seasons
    seasons = [r for r in res if r.get("prec") == "season"]
    by_fr = {}
    for r in seasons:
        by_fr.setdefault((r["franchise_id"], r["role"]), []).append(r)
    for grp in by_fr.values():
        grp.sort(key=lambda r: (r["s_season"], r.get("row_idx", 0)))  # page rows are chronological
        for i, r in enumerate(grp):
            in_season = i > 0 and grp[i - 1]["e_season"] == r["s_season"]
            r["in_season_start"] = in_season
            r["start_date"] = date(r["s_season"] + 1, 1, 15) if in_season else date(r["s_season"], 10, 1)
            r["date_precision_start"] = r["date_precision_end"] = "season"
        for i, r in enumerate(grp):
            if r["e_season"] is None:
                r["end_date"] = None
            elif i + 1 < len(grp) and grp[i + 1]["s_season"] == r["e_season"]:
                r["end_date"] = grp[i + 1]["start_date"]
            else:
                r["end_date"] = date(r["e_season"] + 1, 4, 30)
    return res
