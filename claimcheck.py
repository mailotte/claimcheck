#!/usr/bin/env python3
"""Fail the build when marketing copy and the product drift apart.

Two independent checks over one file, an inventory of the claims your marketing
makes. Together they close a loop that a document alone cannot:

  proof      Every claim stated as shipped must name the automated test that
             backs it, or say plainly that nothing does. A named test that does
             not exist, or no longer contains the named case, fails. The number
             of admittedly-unproven claims is ratcheted: it may fall, never rise.

  citations  Every claim quotes the sentence on the site that makes it, and that
             sentence must still be there. Reword a page and the inventory can no
             longer describe a promise you have stopped making — or one you now
             make more strongly.

The first keeps the inventory honest about the product. The second keeps it
honest about the site. Neither is much use without the other.

Usage:
    claimcheck.py proof [--config PATH] [--update-baseline]
    claimcheck.py citations [--config PATH]
    claimcheck.py all [--config PATH]

Configuration lives in claimcheck.toml beside your repository root; see the
bundled example. Python 3.11+ (tomllib). No dependencies.
"""

from __future__ import annotations

import html
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULTS: dict[str, object] = {
    "inventory": "CLAIMS-INVENTORY.md",
    # Globs, relative to the repository root, for the copy a visitor can read.
    # Point this at what you actually PUBLISH. A working copy-deck that lags the
    # site will happily substantiate a claim no shipped page makes, which is the
    # rot this tool exists to catch.
    "copy_globs": ["site/**/*.html"],
    # Hedges that must carry a proof. A claim the page itself hedges ("beta",
    # "coming soon") has not promised the reader anything yet.
    "requires_proof": "LIVE",
    # Keys a proof annotation may carry. Order does not matter; membership does.
    "proof_keys": ["test"],
    # Claims currently allowed to sit at `unproven`. Lower it when you prove or
    # withdraw one. Raising it is the decision this tool exists to make someone
    # argue for out loud.
    "unproven_baseline": 0,
}


# --- configuration ----------------------------------------------------------

@dataclass(frozen=True)
class Config:
    root: Path
    inventory: Path
    copy_globs: list[str]
    requires_proof: str
    proof_keys: tuple[str, ...]
    unproven_baseline: int
    path: Path | None


def load_config(explicit: str | None) -> Config:
    path = Path(explicit) if explicit else Path("claimcheck.toml")
    data: dict[str, object] = {}
    if path.is_file():
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    elif explicit:
        raise SystemExit(f"config not found: {path}")
    merged = {**DEFAULTS, **data}
    root = Path(str(merged.get("root", "."))).resolve()
    return Config(
        root=root,
        inventory=root / str(merged["inventory"]),
        copy_globs=[str(g) for g in merged["copy_globs"]],  # type: ignore[union-attr]
        requires_proof=str(merged["requires_proof"]),
        proof_keys=tuple(str(k) for k in merged["proof_keys"]),  # type: ignore[union-attr]
        unproven_baseline=int(merged["unproven_baseline"]),  # type: ignore[arg-type]
        path=path if path.is_file() else None,
    )


# --- the inventory format ---------------------------------------------------

# A claim bullet:  - [ ] `[LIVE]` Sorts new mail into two piles.
#
# The marker is CAPTURED, not restricted, on purpose. Matching `[ xX]` directly
# means a bullet written `- [!] ...` — the obvious thing to reach for when an
# audit finds a claim is wrong — does not match at all, so the claim silently
# leaves the contract. That is exactly the zombie claim this checks for, produced
# by the check itself. Unknown markers are a loud failure instead.
CLAIM_RE = re.compile(r"^- \[(?P<marker>.)\] +`\[(?P<hedge>[^\]]+)\]`\s*(?P<text>.+)$")
VALID_MARKERS = {" ", "x", "X"}
PROOF_RE = re.compile(r"<!--\s*proof:\s*(?P<body>.+?)\s*-->")

# A citation is an indented sub-bullet opening with the file it cites:
#     - index.html: "sorts new mail into two piles"
CITATION_RE = re.compile(r"^\s+-\s+(?P<body>\S.*)$")
QUOTE_RE = re.compile(r'"([^"]+)"')
TAG_RE = re.compile(r"<[^>]+>")
# Typographic characters a page renders and a human retypes as ASCII.
FOLD = {"’": "'", "‘": "'", "“": '"', "”": '"', "‑": "-"}


@dataclass
class Claim:
    line: int
    marker: str
    hedge: str
    text: str
    proof: str | None


def parse_claims(path: Path) -> list[Claim]:
    lines = path.read_text(encoding="utf-8").splitlines()
    claims: list[Claim] = []
    for i, raw in enumerate(lines):
        m = CLAIM_RE.match(raw)
        if not m:
            continue
        # The proof annotation is the first one inside this claim's own block,
        # i.e. before the next claim or the next heading.
        proof = None
        for follow in lines[i + 1:]:
            if CLAIM_RE.match(follow) or follow.startswith("#") or follow.startswith("---"):
                break
            pm = PROOF_RE.search(follow)
            if pm:
                proof = pm.group("body")
                break
        claims.append(Claim(i + 1, m.group("marker"), m.group("hedge"), m.group("text"), proof))
    return claims


def field_re(keys: tuple[str, ...]) -> re.Pattern[str]:
    """Match `key=value`, where a value may contain spaces.

    A field ends at the next KNOWN key, not at the next space. Splitting on
    whitespace truncates a test name at its first word, and "does this file
    contain the word 'is'" is true of every file — so the annotation validates
    nothing while reading as proven. Matching only known keys also stops prose in
    an `unproven` reason from being parsed as a field.
    """
    alt = "|".join(re.escape(k) for k in keys)
    return re.compile(
        r"\b(?P<key>" + alt + r")=(?P<value>.*?)(?=\s+\b(?:" + alt + r")=|$)", re.S
    )


def check_proof(body: str, cfg: Config) -> str | None:
    """Validate one proof annotation. Returns an error string, or None."""
    if body.startswith("unproven"):
        # A bare "unproven" is a shrug. Require a reason.
        if not body[len("unproven"):].strip(" —-:"):
            return "`unproven` must be followed by a reason"
        return None

    fields = {
        m.group("key"): m.group("value").strip()
        for m in field_re(cfg.proof_keys).finditer(body)
    }
    if "test" not in fields:
        return f"unrecognised proof {body!r} — expected `test=<path>` or `unproven — <reason>`"

    ref = fields["test"]
    file_part, _, name = ref.partition("::")
    target = cfg.root / file_part
    if not target.is_file():
        return f"test file does not exist: {file_part}"
    if name and name not in target.read_text(encoding="utf-8", errors="replace"):
        return f"{file_part} does not contain {name!r}"
    return None


# --- check 1: every shipped claim names its proof ---------------------------

def run_proof(cfg: Config, update_baseline: bool) -> int:
    if not cfg.inventory.is_file():
        print(f"x {cfg.inventory} not found", file=sys.stderr)
        return 1

    claims = parse_claims(cfg.inventory)
    if not claims:
        # Silent-rot guard. A format change must not read as "nothing to check" —
        # that is a green build over an unenforced contract.
        print(f"x no claims parsed from {cfg.inventory.name} — the format changed.", file=sys.stderr)
        return 1

    failures: list[str] = []
    for claim in claims:
        if claim.marker not in VALID_MARKERS:
            failures.append(
                f"{cfg.inventory.name}:{claim.line}  unknown marker `[{claim.marker}]`"
                f" — use `[ ]` or `[x]`.\n    claim: {claim.text[:90]}\n"
                "    A marker this tool does not know is not a note to the reader,\n"
                "    it is a claim leaving the contract. Say what is wrong in the\n"
                "    proof annotation instead."
            )

    needs_proof = [c for c in claims if cfg.requires_proof in c.hedge]
    unproven = 0
    for claim in needs_proof:
        where = f"{cfg.inventory.name}:{claim.line}"
        if claim.proof is None:
            failures.append(
                f"{where}  no proof annotation\n    claim: {claim.text[:90]}\n"
                "    add:   <!-- proof: test=<path> -->\n"
                "    or:    <!-- proof: unproven — <why> -->"
            )
            continue
        if claim.proof.startswith("unproven"):
            unproven += 1
        err = check_proof(claim.proof, cfg)
        if err:
            failures.append(f"{where}  {err}")

    print(
        f"Claims contract: {len(claims)} claim(s), {len(needs_proof)} marked "
        f"[{cfg.requires_proof}], {unproven} unproven (baseline {cfg.unproven_baseline})."
    )

    if update_baseline:
        # Printed, never written. Raising the ratchet is a decision a human makes
        # in a diff a reviewer can see, not a side effect of running a tool.
        print(f"-> set unproven_baseline = {unproven} in {cfg.path or 'claimcheck.toml'}")
        return 0

    if unproven > cfg.unproven_baseline:
        failures.append(
            f"unproven claims rose to {unproven} (baseline {cfg.unproven_baseline}).\n"
            "    A new claim needs either a proof or an offsetting payment of an\n"
            "    existing gap. Raising the baseline is a decision to market\n"
            "    something nobody has verified — argue for it in review."
        )

    for f in failures:
        print(f"x {f}", file=sys.stderr)
    if failures:
        print(f"\nx {len(failures)} claims-contract failure(s).", file=sys.stderr)
        return 1
    print(f"OK every [{cfg.requires_proof}] claim names its proof.")
    return 0


# --- check 2: every quoted sentence is still on the site --------------------

def normalise(text: str) -> str:
    text = html.unescape(text)
    for bad, good in FOLD.items():
        text = text.replace(bad, good)
    return re.sub(r"\s+", " ", text).strip()


def copy_sources(cfg: Config) -> list[Path]:
    found: set[Path] = set()
    for pattern in cfg.copy_globs:
        found.update(p for p in cfg.root.glob(pattern) if p.is_file())
    return sorted(found)


def corpus(paths: list[Path]) -> str:
    parts = []
    for path in paths:
        raw = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix in {".html", ".htm", ".xml", ".svg"}:
            # Tags become spaces, so "<b>needs you</b>," never fuses into one word.
            raw = TAG_RE.sub(" ", raw)
        parts.append(normalise(raw))
    # A separator no quote can straddle, so a citation cannot "match" by spanning
    # the end of one page and the start of the next.
    return "\n|||\n".join(parts)


def find_citations(
    path: Path, known: set[str]
) -> tuple[list[tuple[int, str, str]], list[tuple[int, str]]]:
    """Return (citations, malformed lines).

    The malformed list exists because of a failure this tool found in its own
    example. A citation whose quote is wrapped across two lines leaves an
    unterminated `"`, the quote regex matches nothing, and the citation
    contributes NOTHING to the check — silently. The claim reads as cited while
    no sentence is verified, which is the precise illusion this tool is for. So a
    citation line with an odd number of quote marks, or with none at all, is a
    failure rather than a skip.
    """
    out: list[tuple[int, str, str]] = []
    malformed: list[tuple[int, str]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        m = CITATION_RE.match(line)
        if not m:
            continue
        body = m.group("body")
        # Only sub-bullets that OPEN with a known source file are citations.
        # Prose lines (NOTE:, CAVEAT:) quote things deliberately — a caveat may
        # name a phrase precisely because you do NOT say it.
        source = next((n for n in sorted(known, key=len, reverse=True) if body.startswith(n)), None)
        if source is None:
            continue
        quotes = QUOTE_RE.findall(body)
        if body.count('"') % 2 or not quotes:
            malformed.append((i, body[:100]))
            continue
        for quote in quotes:
            out.append((i, source, quote))
    return out, malformed


def run_citations(cfg: Config) -> int:
    if not cfg.inventory.is_file():
        print(f"x {cfg.inventory} not found", file=sys.stderr)
        return 1

    paths = copy_sources(cfg)
    if not paths:
        print(f"x no copy matched {cfg.copy_globs} under {cfg.root} — check the globs.", file=sys.stderr)
        return 1

    haystack = corpus(paths)
    cited, malformed = find_citations(cfg.inventory, {p.name for p in paths})
    if not cited:
        print(f"x no citations parsed from {cfg.inventory.name} — the format changed.", file=sys.stderr)
        return 1

    for ln, body in malformed:
        print(
            f"x {cfg.inventory.name}:{ln}  citation has no complete quoted sentence:\n"
            f"    {body}\n"
            "    Keep the quote on ONE line. Wrapped across two it is silently\n"
            "    unchecked, which looks identical to a passing citation.",
            file=sys.stderr,
        )

    failures = [(ln, src, q) for ln, src, q in cited if normalise(q) not in haystack]
    print(f"Claims citations: {len(cited)} quoted citation(s) across {len(paths)} source file(s).")

    for ln, src, quote in failures:
        print(
            f"x {cfg.inventory.name}:{ln}  cited from {src}, but no source contains it:\n"
            f'    "{quote}"',
            file=sys.stderr,
        )
    if malformed and not failures:
        print(f"\nx {len(malformed)} malformed citation(s).", file=sys.stderr)
        return 1
    if failures:
        print(
            f"\nx {len(failures)} dead citation(s). The site changed under the inventory.\n"
            "    Update the quote if you still make the claim in new words; delete the\n"
            "    entry if you no longer make it at all. Do not leave zombie claims.",
            file=sys.stderr,
        )
        return 1
    print("OK every cited line of copy is still published.")
    return 0


# --- entry point ------------------------------------------------------------

def main(argv: list[str]) -> int:
    args = list(argv)
    if not args or args[0] in {"-h", "--help"}:
        print(__doc__)
        return 0 if args else 2
    command = args.pop(0)
    if command not in {"proof", "citations", "all"}:
        print(f"unknown command {command!r}; expected proof, citations or all", file=sys.stderr)
        return 2

    config_path: str | None = None
    if "--config" in args:
        i = args.index("--config")
        try:
            config_path = args[i + 1]
        except IndexError:
            print("--config needs a path", file=sys.stderr)
            return 2
        del args[i:i + 2]
    update_baseline = "--update-baseline" in args
    if update_baseline:
        args.remove("--update-baseline")
    if args:
        print(f"unexpected argument(s): {' '.join(args)}", file=sys.stderr)
        return 2

    cfg = load_config(config_path)
    if command == "proof":
        return run_proof(cfg, update_baseline)
    if command == "citations":
        return run_citations(cfg)
    # `all` runs both and reports both, rather than stopping at the first: the
    # two failures have different causes and you want to see them together.
    return max(run_proof(cfg, update_baseline), run_citations(cfg))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
