from app.discord import pr_embed


def test_pr_author_is_a_small_clickable_github_author():
    embed = pr_embed(
        "Aerya/example",
        {
            "number": 12,
            "html_url": "https://github.com/Aerya/example/pull/12",
            "title": "Update dependency",
            "user": {"login": "dependabot[bot]"},
        },
    )

    assert "thumbnail" not in embed
    assert embed["author"]["url"] == "https://github.com/dependabot%5Bbot%5D"
    assert embed["fields"][1]["value"] == "[dependabot[bot]](https://github.com/dependabot%5Bbot%5D)"
