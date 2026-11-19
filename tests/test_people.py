"""Matching player names from the Telegram posts to one person (no database needed)."""

from app.importers.people import cluster_people, name_tokens


def same(mapping, a, b):
    return mapping[a] == mapping[b]


def test_scripts_word_order_and_suffixes():
    assert name_tokens("Sanzhar Mukimov") == name_tokens("Мукимов Санжар")
    assert name_tokens("Diyorbek Torabek") == name_tokens("Torabekov Diyorbek")
    assert name_tokens("Бекасыл Асанғали") == name_tokens("Bekasyl Asangali")


def test_abbreviations_and_transfers():
    people = {
        ("evolution", "Sanzhar Mukimov"), ("evolution", "Мукимов С."), ("evolution", "Sanzh Mukimov"),
        ("oldschool", "Sanzhar Mukimov"),  # same full name in another team: a transfer
        ("sunkar", "Miras"), ("sunkar", "Miras Serik"),
    }
    m = cluster_people(people)
    assert same(m, ("evolution", "Мукимов С."), ("evolution", "Sanzhar Mukimov"))
    assert same(m, ("evolution", "Sanzh Mukimov"), ("oldschool", "Sanzhar Mukimov"))
    assert same(m, ("sunkar", "Miras"), ("sunkar", "Miras Serik"))


def test_no_merge_when_ambiguous_or_different_teams_for_short_names():
    people = {
        ("sunkar", "Miras"), ("sunkar", "Miras Serik"), ("sunkar", "Miras Bekov"),  # which Miras?
        ("furia", "Miras"),  # single word in another team: not merged
        ("fatih", "Rakhat Zhora"), ("fatih", "Arkhat Amanzholov"), ("fatih", "Rakhat Zhora Arkhat Amanzholov"),
    }
    m = cluster_people(people)
    assert not same(m, ("sunkar", "Miras"), ("sunkar", "Miras Serik"))
    assert not same(m, ("sunkar", "Miras"), ("furia", "Miras"))
    assert not same(m, ("fatih", "Rakhat Zhora"), ("fatih", "Arkhat Amanzholov"))
