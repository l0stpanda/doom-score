"""GM spans for teams whose Wikipedia list gives names without years (Braves, Orioles, Reds), from the
individuals' articles. Team-page order is chronological, so each GM needs only a START; the span ends at the
next GM's start. Evidence, in priority order (D38):
  1 prose sentence with team + 'general manager' + full date (hired/named/promoted/signed...) -> day
  2 prose 'from <Month YYYY>' with team + 'general manager'                                  -> month
  3 prose team + 'general manager' + 'in YYYY' / 'from YYYY'                                 -> year
  4 infobox team range (GM header if present)                                                -> year
Unresolved people go to the manual template; so does the predecessor whose end becomes unknown."""
import json, os, re
from datetime import date
import pandas as pd
import parse_front_office as pf
from fetch_wiki_people import gm_titles, path

NICK = {"atlanta-braves": "Braves", "baltimore-orioles": "Orioles", "cincinnati-reds": "Reds"}
MONTHS = list(pf.MONTHS)
MON = "|".join(m.title() for m in MONTHS)
FULL = re.compile(rf"\b({MON})\s+(\d{{1,2}}),\s+((?:19|20)\d{{2}})")
START_VERB = re.compile(r"hired|named|promot|sign|became|appoint|took over|replac|succeed|elevat", re.I)


def article(title):
    p = path(title)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)["wikitext"]


# sentences about leaving the job / non-GM roles; 'fired'/'released' stay allowed because hiring sentences often
# mention the predecessor's firing ('named GM after the Braves released Frank Wren')
BAD = re.compile(r"resign|consult|before his promotion|assistant general|interview|candidate|considered", re.I)


def evidence(title, fid, earliest_year=1900):
    """Return (start_date, precision, evidence_text) for this person's GM start with team fid, or None.
    Strict on purpose: a wrong span is worse than a template row."""
    t = article(title)
    if t is None:
        return None
    nick = NICK[fid]
    i = t.find("{{Infobox")
    j = t.find("\n}}", i) if i >= 0 else 0
    body = pf.clean(t[j:])
    sents = [s for s in re.split(r"(?<=[.!?])\s+", body) if nick in s and not BAD.search(s)]
    appoint = re.compile(r"(hired|named|promoted|appointed|signed|became|took over)[^.]{0,60}?(general manager|\bGM\b)", re.I)
    for s in sents:  # 1: appointment verb -> 'general manager' + full date
        m = FULL.search(s)
        if m and appoint.search(s):
            d = date(int(m.group(3)), MONTHS.index(m.group(1).lower()) + 1, int(m.group(2)))
            return d, "day", s[:200]
    adj = re.compile(rf"(?:(?:general manager|GM)(?: \(GM\))? (?:of|for|was with) [^.]{{0,40}}?{nick}|{nick}(?:'|’)?s? (?:general manager|GM)"
                     rf"|promoted [^.]{{0,40}}?to general manager)[^.]{{0,40}}?\b(?:from|in|since) "
                     rf"(?:({MON})\s+)?((?:19|20)\d{{2}})")
    for s in sents:  # 2/3: team-adjacent 'from/in [Month] YYYY'
        m = adj.search(s)
        if m:
            y = int(m.group(2))
            if m.group(1):
                return pf.parse_point(f"{m.group(1)} {y}")[0], "month", s[:200]
            return pf.year_boundary(y, "MLB"), "year", s[:200]
    box = t[i:j] if i >= 0 else ""  # 4: executive infobox only (no playing-career fields)
    if box and not re.search(r"\|\s*(debutdate|debut_date|batting|throws|stat1label)\s*=", box) and \
            re.search(r"general manager|executive", box, re.I):
        for line in box.splitlines():
            if nick in line:
                m = re.search(r"((?:19|20)\d{2})\s*(?:–|-|—)", pf.clean(line))
                if m:
                    return pf.year_boundary(int(m.group(1)), "MLB"), "year", "infobox: " + pf.clean(line)[:120]
    return None


def people_spans():
    rows, unresolved = [], []
    for fid, titles in gm_titles().items():
        seq, prev = [], None
        for title in titles:
            ev = evidence(title, fid, 1900)
            if ev and prev and ev[0] < prev[0]:  # out of page order -> not trustworthy
                ev = None
            seq.append((title, ev))
            prev = ev or prev
        for k, (title, ev) in enumerate(seq):
            name = re.sub(r"\s*\(.*\)$", "", title)
            if ev is None:
                unresolved.append(dict(franchise_id=fid, person=name, reason="no start evidence in article"))
                continue
            nxt = seq[k + 1] if k + 1 < len(seq) else None
            if nxt is None:
                end, pe = None, "open"
            elif nxt[1] is None:
                unresolved.append(dict(franchise_id=fid, person=name, reason="end unknown: successor unresolved"))
                continue
            else:
                end, pe = nxt[1][0], nxt[1][1]
            if end is not None and end < ev[0]:
                unresolved.append(dict(franchise_id=fid, person=name, reason="start after successor's start"))
                continue
            rows.append(dict(league="MLB", franchise_id=fid, role="gm", person=name, start_date=ev[0], end_date=end,
                             date_precision_start=ev[1], date_precision_end=pe, interim=False,
                             source_url=pf.url(title), evidence=ev[2], needs_verification=True))
    return pd.DataFrame(rows), pd.DataFrame(unresolved)


if __name__ == "__main__":
    s, u = people_spans()
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 90)
    print(s[s.end_date.isna() | (s.end_date.map(lambda d: d is not None and d >= date(1999, 1, 1)))]
          [["franchise_id", "person", "start_date", "end_date", "date_precision_start", "evidence"]].to_string(index=False))
    print("\nUNRESOLVED:\n", u.to_string(index=False))
