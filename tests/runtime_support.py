"""Explicit test doubles. They provide no evidence of real Jev/engineering performance."""

from guacamole import (
    Candidate,
    DecisionRequest,
    DecisionResult,
    DeliverableSpec,
    WorkPlan,
)


class TestJev:
    name = "test-double-jev"
    version = "1"
    is_test_double = True

    def __init__(self):
        self.calls = []
        self.abstain = False

    async def decide(self, request_id, request):
        self.calls.append(request)
        return DecisionResult(
            request_id=request_id,
            selected=None if self.abstain else request.candidates[0].id,
            explanation="TEST DOUBLE: first eligible fixture candidate",
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
