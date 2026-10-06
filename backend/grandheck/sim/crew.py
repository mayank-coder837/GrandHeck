"""Worker profiles: the fixed demo crew, and random crews for the evaluation."""

from __future__ import annotations

import random

from ..schema import WorkerProfile

DEMO_CREW = [
    WorkerProfile(worker_id="W1", name="Omar Haddad", role="Driller", age=38, acclimatized=True, workload="heavy"),
    WorkerProfile(worker_id="W2", name="Ravi Menon", role="Welder", age=29, acclimatized=True, workload="moderate"),
    WorkerProfile(worker_id="W3", name="Daniel Okafor", role="Labourer (new)", age=24, acclimatized=False, workload="heavy"),
    WorkerProfile(worker_id="W4", name="Sara Lindqvist", role="Surveyor", age=31, acclimatized=True, workload="light"),
    WorkerProfile(worker_id="W5", name="Yusuf Rahman", role="Pipefitter", age=52, acclimatized=True, workload="moderate"),
    WorkerProfile(worker_id="W6", name="Li Wei", role="Electrician (new)", age=41, acclimatized=False, workload="moderate"),
    WorkerProfile(worker_id="W7", name="Mateo Rossi", role="Rigger", age=46, acclimatized=True, workload="heavy"),
    WorkerProfile(worker_id="W8", name="Aisha Karimi", role="Safety officer", age=36, acclimatized=True, workload="light"),
]


def random_crew(rng: random.Random, size: int = 8) -> list[WorkerProfile]:
    crew = []
    for i in range(size):
        crew.append(WorkerProfile(
            worker_id=f"R{i + 1}",
            name=f"Worker {i + 1}",
            role="Crew",
            age=rng.randint(20, 60),
            acclimatized=rng.random() < 0.7,
            workload=rng.choices(["light", "moderate", "heavy"], weights=[0.3, 0.45, 0.25])[0],
        ))
    return crew
