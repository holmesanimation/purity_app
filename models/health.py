from dataclasses import dataclass


@dataclass
class HealthMetrics:
    sleep_hours: float
    hydration_glasses: int
    hydration_target: int
    workout_done: bool
    protein_g: int
    protein_target: int
    caffeine_cups: int
