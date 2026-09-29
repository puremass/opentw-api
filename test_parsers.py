"""Offline checks for the parsing helpers - no network, runs in a second:

    python test_parsers.py

Each case is a shape that TrackWrestling has served, or one that broke a parser before.
smoke_test.py covers the live site; this covers the edges the live site may not show today.
"""
import sys
from datetime import date

from parsers.tournaments import (
    _parse_date_range,
    _parse_weights,
    _split_js_args,
    parse_bracket_data,
)

failures: list[str] = []


def check(label: str, actual, expected) -> None:
    ok = actual == expected
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f"  - got {actual!r}, expected {expected!r}"))
    if not ok:
        failures.append(label)


print("date ranges")
check("both years", _parse_date_range("03/19/2026 - 03/21/2026"), (date(2026, 3, 19), date(2026, 3, 21)))
check("start borrows end's year", _parse_date_range("03/19 - 03/21/2026"), (date(2026, 3, 19), date(2026, 3, 21)))
check("range across New Year", _parse_date_range("12/30 - 01/02/2027"), (date(2026, 12, 30), date(2027, 1, 2)))
check("single day", _parse_date_range("03/19/2026"), (date(2026, 3, 19), None))
check("unparseable", _parse_date_range("TBD"), (None, None))

print("js args")
check("comma in name", _split_js_args("123,'Some Open, 3rd-4th Grade',1,'logo.png'"),
      ["123", "Some Open, 3rd-4th Grade", "1", "logo.png"])
check("bracket in name", _split_js_args("5,'NCAA League Tournament (Boys)',1,'null'"),
      ["5", "NCAA League Tournament (Boys)", "1", "null"])
check("escaped quote in name", _split_js_args(r"7,'St. Mary\'s Open',2,'null'"),
      ["7", "St. Mary's Open", "2", "null"])
check("escaped backslash", _split_js_args(r"8,'A\\B',2,'null'"), ["8", "A\\B", "2", "null"])

print("weights")
# 12 entries fit both a 3-field and a 4-field reading when names are numeric, so the
# shape has to come from the layout. This is the reviewer's example, old format.
old = _parse_weights("1~11~125~5~1~12~133~5~1~13~141~5", with_division=True)
check("old shape: names", [w.weight_name for w in old], ["125", "133", "141"])
check("old shape: ids", [(w.division_id, w.weight_id, w.bracket_id) for w in old], [(1, 11, 5), (1, 12, 5), (1, 13, 5)])
new = _parse_weights("11~125~5~12~133~5~13~141~5~14~149~5", with_division=False)
check("new shape: names", [w.weight_name for w in new], ["125", "133", "141", "149"])
check("new shape: no division", {w.division_id for w in new}, {None})

print("bracket page layouts")


def page(*payloads: str) -> str:
    body = "\n".join(f'str = "{p}";' for p in payloads)
    return f"<script>var p = new Pile();\n{body}</script>"


template = "4~0~Default Template~670~870~8~4,Top Bracket,5,Bottom Bracket"
four = parse_bracket_data(page(template, "1~Varsity", "1~11~125~4~1~12~133~4~1~13~141~4", "4"))
check("4 blocks: divisions", [d.division_name for d in four.divisions], ["Varsity"])
check("4 blocks: weights", [w.weight_name for w in four.weights], ["125", "133", "141"])
three = parse_bracket_data(page(template, "11~125~4~12~133~4~13~141~4~14~149~4", "4"))
check("3 blocks: weights", [w.weight_name for w in three.weights], ["125", "133", "141", "149"])

with open("htmls/brackets.html", encoding="utf-8", errors="replace") as fh:
    captured = parse_bracket_data(fh.read())
check("captured page: first weight", captured.weights[0].weight_name, "106")

print()
if failures:
    print(f"{len(failures)} FAILED: " + "; ".join(failures))
    sys.exit(1)
print("all checks passed")
