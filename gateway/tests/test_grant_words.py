"""Plain words for grants (OpenSpec add-scope-requests): never narrower than what is enforced."""

from gateway.lib.grant_words import entry_words


def test_no_school_constraint_says_every_school():
    entry = {"server": "pupil-data", "tools": ["search"]}
    assert "at every school" in entry_words(entry)


def test_a_school_constraint_names_the_school():
    entry = {"server": "directory", "tools": ["roster"], "constraints": {"urn": ["SCH04"]}}
    words = entry_words(entry)
    assert "Dunmore Community College (SCH04)" in words
    assert "every school" not in words


def test_files_and_labels_are_not_per_school():
    assert "school" not in entry_words({"server": "pupil-data", "tools": ["get", "classification"]})


def test_row_cap_and_rate_are_shown():
    entry = {"server": "directory", "tools": ["roster"], "constraints": {"urn": ["SCH04"]}, "max_rows": 20,
             "rate": {"per_minute": 5, "max_calls": 40}}  # fmt: skip
    words = entry_words(entry)
    assert "at most 20 rows a call" in words
    assert "at most 5 calls a minute" in words
    assert "40 calls in all" in words
