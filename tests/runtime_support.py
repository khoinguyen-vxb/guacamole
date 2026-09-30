"""Labelled reasoning fixtures; they provide no engineering performance evidence."""

from guacamole import (
    Candidate,
    DecisionRequest,
    DeliverableSpec,
    WorkPlan,
)


class TestReasoning:
    name = "test-double-reasoning"
    model = "scripted-fixture"
    context_capacity_tokens = 500_000

    async def count_tokens(self, prompt):
        # Exact count for this fake provider's one-byte token alphabet.
        return len(prompt.encode())


def plan_request(requirement, *, stage="PDR", tools=(), tasks=()):
    return DecisionRequest(
        question="Select a fixture work plan",
        kind="work_plan",
        criteria=("Typed fixture coverage",),
        candidates=(
            Candidate(
                id="fixture",
                description="TEST ONLY",
                plan=WorkPlan(
                    stage=stage,
                    inputs=(requirement,),
                    chief_tools=tools,
                    tasks=tasks,
                    deliverables=(
                        DeliverableSpec(
                            id=stage + "-design",
                            title="Fixture",
                            stage=stage,
                            requirements=(requirement,),
                            artifact_kinds=("editable-design",),
                            evidence_kinds=("verification",),
                            acceptance_criteria=(
                                "Fixture file has the required value",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
