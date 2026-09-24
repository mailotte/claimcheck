# Example claims inventory

Each claim is one bullet. The hedge in backticks says how the page states it;
only `[LIVE]` claims must carry a proof. Under each claim:

- a `<!-- proof: ... -->` annotation, naming the test or admitting there is none
- one citation per page that makes the claim, quoting the exact words

## Sorting

- [x] `[LIVE]` Sorts new mail into two piles: needs you, and handled.
  <!-- proof: test=tests/test_sorting.py::test_new_mail_lands_in_one_of_two_piles -->
  - index.html: "sorts new mail into two piles"

- [x] `[LIVE]` A correction overrides the rules for that sender.
  <!-- proof: test=tests/test_sorting.py::test_a_correction_beats_the_rules -->
  - index.html: "Correct it once and it stays corrected"

- [ ] `[LIVE]` Your mail is never used to train a model.
  <!-- proof: unproven — conduct and contract, not behaviour; a green test here would be false comfort -->
  - index.html: "never used to train a model"

## Not yet shipped

- [ ] `[BETA]` Reply drafts in your own tone.
  - index.html: "drafts in your own tone (beta)"
