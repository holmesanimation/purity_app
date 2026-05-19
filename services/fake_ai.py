class FakeAIService:
    _weekly_report = (
        "This week showed meaningful progress. You maintained your streak through several "
        "high-risk moments and chose connection over isolation. Your journaling reflected "
        "a deepening awareness of triggers — especially boredom and late-evening fatigue. "
        "The Holy Spirit is at work. Keep leaning in."
    )

    _categories = [
        ("Boredom / Idle Time", 4),
        ("Late Evening", 3),
        ("Stress / Work Pressure", 2),
        ("Social Isolation", 1),
    ]

    _suggestions = [
        "Replace late-night phone time with a short prayer walk or reading.",
        "When boredom hits, text a friend or pick up your Bible before opening apps.",
        "Schedule one accountability check-in this week.",
        "Add a brief gratitude note each morning before checking your phone.",
        "Consider a digital sunset — all screens off 30 minutes before bed.",
    ]

    _encouragement_insights = [
        "You are not fighting alone. Every step forward is a victory worth celebrating.",
        "His mercies are new every morning. Today is a fresh start.",
        "Strength is built in the small, faithful choices — you're making them.",
        "The battle is real, but so is the victory already won for you.",
        "Walk in the Spirit and you will not gratify the desires of the flesh. — Gal 5:16",
    ]

    def get_weekly_report(self) -> str:
        return self._weekly_report

    def get_categories(self) -> list[tuple[str, int]]:
        return list(self._categories)

    def get_suggestions(self) -> list[str]:
        return list(self._suggestions)

    def get_encouragement_insight(self) -> str:
        import random
        return random.choice(self._encouragement_insights)
