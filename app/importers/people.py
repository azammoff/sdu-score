"""Decide which player names in the channel posts belong to the same person.

The posts spell people in many ways:
    "Sanzhar Mukimov", "Мукимов С.", "Mukimov Sanzhar"
    "Diyorbek Torabekov", "Torabek Diyorbek", "Диёрбек Торабеков"
and players move between teams over the seasons.

Rules (from safest to riskiest):
1. Same team, same normalized name (any script, any word order) -> same person.
2. Same team, one name is an abbreviation of the other ("Mukimov S." vs "Sanzhar Mukimov"),
   or a single word that fits exactly one full name in that team ("Miras" vs "Miras Serik") -> same person.
3. Different teams, same normalized *full* name (two or more words) -> same person (a transfer).
"""

import re
import unicodedata
from collections import defaultdict

CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
    "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
    # Kazakh
    "ә": "a", "ғ": "g", "қ": "k", "ң": "n", "ө": "o", "ұ": "u", "ү": "u", "һ": "h", "і": "i",
}
SUFFIXES = ("ova", "eva", "ov", "ev", "uli", "kizi")


def _latin(text: str) -> str:
    text = "".join(CYRILLIC.get(ch, ch) for ch in text.lower())
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return text.replace("ı", "i")


def _token(word: str) -> str:
    """Normalize one word so that common spelling variants become equal."""
    w = re.sub(r"[^a-z]", "", _latin(word))
    for a, b in (("dzh", "j"), ("zh", "j"), ("kh", "h"), ("ts", "c"), ("y", "i"), ("w", "u"), ("x", "h")):
        w = w.replace(a, b)
    w = re.sub(r"(.)\1+", r"\1", w)  # double letters
    for suffix in SUFFIXES:
        if w.endswith(suffix) and len(w) - len(suffix) >= 4:
            w = w[: -len(suffix)]
            break
    return w


def name_tokens(name: str) -> tuple[str, ...]:
    return tuple(sorted(t for t in (_token(part) for part in re.split(r"[\s.\-]+", name)) if t))


def _full(tokens: tuple[str, ...]) -> list[str]:
    return [t for t in tokens if len(t) >= 2]


MAX_WORDS = 3  # longer "names" are two names glued together by a typo in the post


def _abbreviates(short: tuple[str, ...], long: tuple[str, ...]) -> bool:
    """'mukim s' / 'mukim sanj' abbreviate 'mukim sanjar': each word is equal to, an initial of,
    or a shortened form of a different word of the long name."""
    if not short or len(short) > len(long) or short == long or len(long) > MAX_WORDS:
        return False
    remaining = list(long)
    full_hits = 0
    for t in sorted(short, key=len, reverse=True):
        match = next((r for r in remaining if r == t), None)
        if match:
            full_hits += 1
        elif len(t) == 1 or len(t) >= 3:
            match = next((r for r in remaining if r.startswith(t)), None)
        if match is None:
            return False
        remaining.remove(match)
    return full_hits >= 1


class _UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        self.parent[self.find(a)] = self.find(b)


def cluster_people(appearances: set[tuple[str, str]]) -> dict[tuple[str, str], tuple[str, str]]:
    """Map every (team_key, raw_name) to a representative (team_key, raw_name) of the same person."""
    uf = _UnionFind()
    tokens = {a: name_tokens(a[1]) for a in appearances}
    for a in appearances:
        uf.find(a)

    # 1. same team, same tokens
    by_team_tokens = defaultdict(list)
    for a, t in tokens.items():
        if t:
            by_team_tokens[(a[0], t)].append(a)
    for group in by_team_tokens.values():
        for other in group[1:]:
            uf.union(other, group[0])

    # 3. same full name across teams
    by_tokens = defaultdict(list)
    for a, t in tokens.items():
        if len(_full(t)) >= 2 and len(t) <= MAX_WORDS and all(len(x) >= 3 for x in _full(t)):
            by_tokens[t].append(a)
    for group in by_tokens.values():
        for other in group[1:]:
            uf.union(other, group[0])

    # 2. abbreviations / single words inside one team, only when they point to exactly one person
    by_team = defaultdict(set)
    for (team, _), t in tokens.items():
        if t:
            by_team[team].add(t)
    changed = True
    while changed:  # repeat: one merge can make another abbreviation unambiguous
        changed = False
        for team, names in by_team.items():
            for short in names:
                candidates = [long for long in names if _abbreviates(short, long)]
                people = {uf.find(by_team_tokens[(team, long)][0]) for long in candidates}
                me = uf.find(by_team_tokens[(team, short)][0])
                if len(people) == 1 and me not in people:
                    uf.union(me, people.pop())
                    changed = True

    return {a: uf.find(a) for a in appearances}
