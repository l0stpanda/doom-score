"""Phase 2 fetch: drafts, MLB managers, MLB attendance, Wikipedia front-office pages.
Uses the cached getter from Phase 1 (data/raw/<source>/, never re-downloads)."""
import json, os, sys
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_phase1 import get, RAW

UA = {"User-Agent": "doom-score-research/0.1 (student project; python-requests)"}


def _install_ua():
    """Send a descriptive User-Agent from the Phase 1 getter. Only called from main() (no import side effect)."""
    orig = requests.get
    requests.get = lambda url, timeout=30, **kw: orig(url, timeout=timeout, headers=UA, **kw)

MLB_DRAFT = "https://statsapi.mlb.com/api/v1/draft/{y}"
NHL_DRAFT = "https://api-web.nhle.com/v1/draft/picks/{y}/all"
MLB_COACH = "https://statsapi.mlb.com/api/v1/teams/{tid}/coaches?season={y}"
MLB_COACH_DATE = "https://statsapi.mlb.com/api/v1/teams/{tid}/coaches?date={d}"
MLB_SEASON = "https://statsapi.mlb.com/api/v1/seasons/{y}?sportId=1"
MLB_ATT = "https://statsapi.mlb.com/api/v1/attendance?leagueId=103,104&season={y}"
WIKI = "https://en.wikipedia.org/w/api.php?action=parse&page={p}&prop=wikitext&redirects=1&format=json&formatversion=2"

# Wikipedia pages per franchise_id. Order matters only for readability; all spans are pooled.
MLB_EXEC_PAGES = {  # franchise_id -> "owners and executives" page
    "arizona-diamondbacks": "Arizona Diamondbacks", "athletics": "Athletics", "atlanta-braves": "Atlanta Braves",
    "baltimore-orioles": "Baltimore Orioles", "boston-red-sox": "Boston Red Sox", "chicago-cubs": "Chicago Cubs",
    "chicago-white-sox": "Chicago White Sox", "cincinnati-reds": "Cincinnati Reds",
    "cleveland-guardians": "Cleveland Guardians", "colorado-rockies": "Colorado Rockies",
    "detroit-tigers": "Detroit Tigers", "houston-astros": "Houston Astros", "kansas-city-royals": "Kansas City Royals",
    "los-angeles-angels": "Los Angeles Angels", "los-angeles-dodgers": "Los Angeles Dodgers",
    "miami-marlins": "Miami Marlins", "milwaukee-brewers": "Milwaukee Brewers", "minnesota-twins": "Minnesota Twins",
    "new-york-mets": "New York Mets", "new-york-yankees": "New York Yankees",
    "philadelphia-phillies": "Philadelphia Phillies", "pittsburgh-pirates": "Pittsburgh Pirates",
    "san-diego-padres": "San Diego Padres", "san-francisco-giants": "San Francisco Giants",
    "seattle-mariners": "Seattle Mariners", "st-louis-cardinals": "St. Louis Cardinals",
    "tampa-bay-rays": "Tampa Bay Rays", "texas-rangers": "Texas Rangers", "toronto-blue-jays": "Toronto Blue Jays",
    "washington-nationals": "Washington Nationals",
}
NHL_NAMES = {  # franchise_id -> names whose list pages to fetch
    "anaheim-ducks": ["Anaheim Ducks"], "boston-bruins": ["Boston Bruins"], "buffalo-sabres": ["Buffalo Sabres"],
    "calgary-flames": ["Calgary Flames"], "carolina-hurricanes": ["Carolina Hurricanes"],
    "chicago-blackhawks": ["Chicago Blackhawks"], "colorado-avalanche": ["Colorado Avalanche"],
    "columbus-blue-jackets": ["Columbus Blue Jackets"], "dallas-stars": ["Dallas Stars"],
    "detroit-red-wings": ["Detroit Red Wings"], "edmonton-oilers": ["Edmonton Oilers"],
    "florida-panthers": ["Florida Panthers"], "los-angeles-kings": ["Los Angeles Kings"],
    "minnesota-wild": ["Minnesota Wild"], "montreal-canadiens": ["Montreal Canadiens"],
    "nashville-predators": ["Nashville Predators"], "new-jersey-devils": ["New Jersey Devils"],
    "new-york-islanders": ["New York Islanders"], "new-york-rangers": ["New York Rangers"],
    "ottawa-senators": ["Ottawa Senators"], "philadelphia-flyers": ["Philadelphia Flyers"],
    "pittsburgh-penguins": ["Pittsburgh Penguins"], "san-jose-sharks": ["San Jose Sharks"],
    "seattle-kraken": ["Seattle Kraken"], "st-louis-blues": ["St. Louis Blues"],
    "tampa-bay-lightning": ["Tampa Bay Lightning"], "toronto-maple-leafs": ["Toronto Maple Leafs"],
    "utah-mammoth": ["Arizona Coyotes", "Utah Mammoth"], "vancouver-canucks": ["Vancouver Canucks"],
    "vegas-golden-knights": ["Vegas Golden Knights"], "washington-capitals": ["Washington Capitals"],
    "winnipeg-jets": ["Atlanta Thrashers", "Winnipeg Jets"],
}


def wiki_pages():
    pages = [f"List of {n} owners and executives" for n in MLB_EXEC_PAGES.values()]
    for names in NHL_NAMES.values():
        for n in names:
            pages += [f"List of {n} general managers", f"List of {n} head coaches"]
    return sorted(set(pages))


def wiki(page):
    return get("wikipedia", page.replace("/", "_"), WIKI.format(p=requests.utils.quote(page)))


def mlb_team_ids():
    return [t["id"] for t in f1_load("mlb_meta", "teams_2026")["teams"]]


def f1_load(src, name):
    with open(os.path.join(RAW, src, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def main():
    _install_ua()
    for name, url in [("mlb_draft/2010", MLB_DRAFT.format(y=2010)), ("nhl_draft/2010", NHL_DRAFT.format(y=2010)),
                      ("mlb_coaches/147_2010", MLB_COACH.format(tid=147, y=2010)),
                      ("mlb_attendance/2010", MLB_ATT.format(y=2010)), ("mlb_seasons/2010", MLB_SEASON.format(y=2010))]:
        s, n = name.split("/")
        print(f"probe {name}: {'ok' if get(s, n, url) is not None else 'BLOCKED/ERROR'}")
    print(f"probe wikipedia: {'ok' if wiki('List of Boston Bruins head coaches') else 'BLOCKED/ERROR'}")

    for y in range(1997, 2027):
        ok = get("mlb_draft", str(y), MLB_DRAFT.format(y=y)) is not None
        ok2 = get("mlb_attendance", str(y), MLB_ATT.format(y=y)) is not None
        print(f"MLB draft {y}: {'ok' if ok else 'FAILED'} | attendance: {'ok' if ok2 else 'FAILED'}")
    for y in [2002, 2003] + list(range(2005, 2026)):
        print(f"NHL draft {y}: {'ok' if get('nhl_draft', str(y), NHL_DRAFT.format(y=y)) is not None else 'FAILED'}")

    tids = mlb_team_ids()
    for y in range(1990, 2027):
        get("mlb_seasons", str(y), MLB_SEASON.format(y=y))
        fails = 0
        for tid in tids:
            r = get("mlb_coaches", f"{tid}_{y}", MLB_COACH.format(tid=tid, y=y))
            if r is None:
                fails += 1
                continue
            mgrs = [x for x in r.get("roster", []) if "Manager" in x.get("job", "") and "Coach" not in x.get("job", "")
                    and "General" not in x.get("job", "")]
            if len(mgrs) > 1:  # in-season change: who was in charge at season end?
                end = f1_load("mlb_seasons", str(y))["seasons"][0]["regularSeasonEndDate"]
                get("mlb_coaches_end", f"{tid}_{y}", MLB_COACH_DATE.format(tid=tid, d=end))
        print(f"MLB managers {y}: {len(tids) - fails}/{len(tids)} ok")

    for p in wiki_pages():
        print(f"wiki {p}: {'ok' if wiki(p) is not None else 'FAILED'}")


if __name__ == "__main__":
    main()
