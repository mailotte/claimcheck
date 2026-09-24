"""The tests the inventory points at. Delete one and `claimcheck proof` fails."""


def test_new_mail_lands_in_one_of_two_piles() -> None:
    assert sort("invoice due friday") in {"needs-you", "handled"}


def test_a_correction_beats_the_rules() -> None:
    """The claim is that a correction WINS, so the rule must lose to it."""
    correct("newsletter@example.com", "needs-you")
    assert sort_from("newsletter@example.com") == "needs-you"


# --- the stand-in "product" -------------------------------------------------
_CORRECTIONS: dict[str, str] = {}
_RULES = {"newsletter@example.com": "handled"}


def sort(_subject: str) -> str:
    return "needs-you"


def correct(sender: str, pile: str) -> None:
    _CORRECTIONS[sender] = pile


def sort_from(sender: str) -> str:
    # Corrections are consulted BEFORE the rules. Reverse these two lines and
    # the correction test fails, which is the point.
    if sender in _CORRECTIONS:
        return _CORRECTIONS[sender]
    return _RULES.get(sender, "needs-you")
