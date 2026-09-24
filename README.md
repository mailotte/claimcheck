# claimcheck

Fail the build when your marketing copy and your product drift apart.

Every claim your site makes must name the automated test that backs it, or admit
that nothing does. Every claim must also quote the sentence on the site that
makes it, and that sentence must still be there. Break either link and CI goes
red.

One file, no dependencies, Python 3.11+.

```
$ python3 claimcheck.py all
Claims contract: 4 claim(s), 3 marked [LIVE], 1 unproven (baseline 1).
OK every [LIVE] claim names its proof.
Claims citations: 4 quoted citation(s) across 1 source file(s).
OK every cited line of copy is still published.
```

This is the tool described in
[Our CI fails the build when our marketing lies](https://mailotte.com/blog/our-ci-fails-when-our-marketing-lies.html),
extracted from [Mailotte](https://mailotte.com)'s own repository and
generalised. It is what we actually run, not a demo.

## Why two checks

A list of marketing promises, kept in a document, rots in two directions and
each direction needs its own check.

**Toward the product.** A claim gets written, the feature changes under it, and
nobody reconciles the two. `proof` makes each claim name a test. Delete the
test and the build fails, so the claim cannot quietly outlive the behaviour it
describes.

**Toward the site.** Somebody rewords a page. Now the inventory catalogues
promises you have stopped making, and — worse — cannot see promises you have
started making more strongly. `citations` makes each claim quote the live copy,
so a page rewrite either updates the inventory or goes red.

Running only the first gives you a contract about a site that shipped weeks ago.
Running only the second gives you copy that matches an unverified product.

## The inventory format

```markdown
- [x] `[LIVE]` Sorts new mail into two piles: needs you, and handled.
  <!-- proof: test=tests/test_sorting.py::test_new_mail_lands_in_one_of_two_piles -->
  - index.html: "sorts new mail into two piles"

- [ ] `[LIVE]` Your mail is never used to train a model.
  <!-- proof: unproven — conduct and contract, not behaviour; a green test here would be false comfort -->
  - index.html: "never used to train a model"

- [ ] `[BETA]` Reply drafts in your own tone.
  - index.html: "drafts in your own tone (beta)"
```

- The hedge in backticks is **how the page states the claim**. Only claims
  stated as shipped (`requires_proof`, default `LIVE`) need proof; a claim the
  page itself hedges has not promised the reader anything yet.
- `test=<path>` must exist. With `::name`, the file must contain that name.
- `unproven` is a first-class answer, and requires a reason. Most claims at most
  companies have no automated proof, and pretending otherwise is worse than
  saying so.
- **`unproven` is ratcheted.** The count may fall, never rise. A new claim needs
  either a proof or an offsetting payment of an existing gap. That is the whole
  mechanism: it makes "let's just say it" a conversation instead of a commit.

Run `claimcheck.py proof --update-baseline` to see the current count. It prints
the new value rather than writing it, because raising the ratchet should appear
in a diff a reviewer can see.

## Configuration

`claimcheck.toml` in the working directory, or `--config PATH`:

```toml
root = "."
inventory = "marketing/CLAIMS-INVENTORY.md"
copy_globs = ["marketing/site/**/*.html", "marketing/site/*.txt"]
requires_proof = "LIVE"
proof_keys = ["test", "route"]
unproven_baseline = 0
```

Point `copy_globs` at what you **publish**. A working copy-deck that lags the
site will cheerfully substantiate a claim no shipped page makes, which is the
drift this tool exists to catch.

## Try it

The repository ships a worked example — an inventory, a one-page site, and the
tests it points at:

```bash
python3 claimcheck.py all        # passes
python3 -m pytest example/tests  # the tests the inventory names
```

Then break it, which is the only way to trust it:

| Do this | What happens |
|---|---|
| Delete `example/tests/test_sorting.py` | `test file does not exist` |
| Rename a test the inventory names | `does not contain 'test_...'` |
| Reword `sorts new mail into two piles` on the page | `cited from index.html, but no source contains it` |
| Add a `[LIVE]` claim marked `unproven` | `unproven claims rose to 2 (baseline 1)` |
| Change a claim's `[x]` to `[!]` | `unknown marker` |

## Design notes, including the sharp edges

These are the mistakes the tool is shaped around. Several were found the
expensive way.

**An unknown marker is a failure, not a skip.** The claim regex *captures* the
checkbox marker instead of matching `[ xX]`. If it matched directly, a bullet
written `- [!] ...` — the obvious thing to reach for when an audit finds a claim
is wrong — would not match at all, and the claim would silently leave the
contract. That is the exact zombie claim the tool is for, produced by the tool.

**A proof field ends at the next known key, not the next space.** Test names
contain spaces (`it('registers navigate / compose / search')`). Splitting on
whitespace truncates the name to its first word, and "does this file contain the
word `is`" is true of every file — so the annotation validates nothing while
reading as proven.

**Pages are joined by a separator no quote can straddle**, so a citation cannot
match by spanning the end of one page and the start of the next.

**Parsing nothing is a failure.** If the inventory's format changes and no claim
or citation parses, the tool fails instead of reporting success. A green build
over an unenforced contract is worse than a red one.

**A citation must keep its quote on one line.** Wrapped across two, the quote is
unterminated, the regex matches nothing, and the citation would contribute
nothing while looking exactly like a passing one. The tool now fails on a
citation line with no complete quoted sentence. (This tool found that in its own
example, which is a fair advertisement for writing the failing case first.)

**Quotes match case-sensitively**, after stripping HTML tags, unescaping
entities, folding typographic quotes to ASCII and collapsing whitespace. Case is
deliberate: `Never` and `never` can differ in force at the start of a sentence.

### What it cannot do

- **`test=` is a substring search over the file.** A mention of the test's name
  in a comment satisfies it. It is that way on purpose — the tool has to work for
  pytest, vitest, Go and anything else — but it means a careless rename can leave
  a proof pointing at a comment. If that matters to you, name the test in a way
  that only its definition would contain.
- **It checks code and configuration, not production.** A test can prove the code
  only ever calls EU providers; it cannot prove the running system has not
  drifted. Claims about live behaviour still need someone to measure production,
  and the test then pins the copy to what was measured.
- **It only knows the claims someone wrote down.** A sentence nobody adds to the
  inventory has no proof and no guard. This tool makes claims *honest*, not
  *complete*.
- **A test can be too weak.** "The page contains this sentence" proves the page,
  not the product. The useful proofs trace the sentence to the code that makes it
  true. Mutation-test them: invert the behaviour and watch the test go red. A
  green test that cannot fail proves nothing.

## Licence

MIT. See [LICENSE](LICENSE).
