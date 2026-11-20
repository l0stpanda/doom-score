"""Phase 4 fetch (money). Cached; BLOCKED sources are not retried.
- Cot's Baseball Contracts team pages (payroll history table 2000-2026) + CBA history page.
- Lahman Salaries.csv mirror (cross-check, <=2016).
- Wikipedia NHL salary cap page (cap ceiling by season) via the approved Action API method."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_phase3 import get
from fetch_wiki_batch import API

COTS = "https://legacy.baseballprospectus.com/compensation/cots/"
LAHMAN = "https://raw.githubusercontent.com/seanlahman/baseballdatabank/master/core/Salaries.csv"


def cots_team_urls():
    idx = get("cots", "index", COTS, kind="csv")  # html stored as text
    urls = sorted(set(re.findall(r'href="(https?://legacy\.baseballprospectus\.com/compensation/cots/'
                                 r'(?:al|nl|american-league|national-league)[^/"]*/[a-z-]+/)"', idx)))
    return [u for u in urls if "oakland-athletics" not in u]


def main():
    urls = cots_team_urls()
    print(f"Cot's team pages found: {len(urls)}", flush=True)
    ok = 0
    for u in urls:
        name = u.rstrip("/").split("/")[-1]
        ok += get("cots", name, u, kind="csv") is not None
    print(f"Cot's team pages fetched: {ok}/{len(urls)}", flush=True)
    for name in ("cba-history",):
        r = get("cots", name, COTS + f"league-info/{name}/", kind="csv")
        print(f"Cot's {name}: {'ok' if r else 'FAILED'}", flush=True)
    print(f"Lahman Salaries: {'ok' if get('lahman', 'Salaries', LAHMAN, kind='csv') else 'FAILED'}", flush=True)
    r = get("wikipedia_money", "nhl_salary_cap", API + "?action=parse&page=National_Hockey_League_salary_cap"
            "&prop=wikitext&format=json&formatversion=2")
    print(f"Wikipedia NHL salary cap: {'ok' if r else 'FAILED'}", flush=True)


if __name__ == "__main__":
    main()
