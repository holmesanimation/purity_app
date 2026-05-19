from models.health import HealthMetrics
from models.goals import Goal


class MockAppState:
    """Singleton holding all fake runtime state for the prototype."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.purity_streak_days = 12
        self.health = HealthMetrics(
            sleep_hours=7.0,
            hydration_glasses=5,
            hydration_target=8,
            workout_done=False,
            protein_g=110,
            protein_target=160,
            caffeine_cups=2,
        )
        self.energy_level = "Medium"
        self.today_verse = {
            "reference": "Philippians 4:13",
            "text": "I can do all things through Christ who strengthens me.",
        }
        self.risk_level = "low"  # "low" | "medium" | "high"
        self.last_checkin_mood = "😐"
        self.current_focus_state = "Strong state"
        self.goals = [
            Goal(
                id="g1",
                title="No unplanned browsing",
                why="Guard my mind",
                daily_actions=["Use browser intentionally", "No news sites"],
                completed_today=False,
            ),
            Goal(
                id="g2",
                title="Morning prayer",
                why="Start the day anchored",
                daily_actions=["Pray before phone", "Journal one verse"],
                completed_today=True,
            ),
            Goal(
                id="g3",
                title="Evening shutdown ritual",
                why="Rest well, no late temptations",
                daily_actions=["Devices off at 9pm", "Read before sleep"],
                completed_today=False,
            ),
        ]

    def set_goal_completed(self, goal_id: str, value: bool):
        for g in self.goals:
            if g.id == goal_id:
                g.completed_today = value
                break
