import json
import tempfile
import unittest
from pathlib import Path

from runtime_support import TestReasoning, commit_fixture_model, plan_request

from guacamole import (
    AgentTurn,
    ArtifactRecord,
    ContextSpec,
    Deliverable,
    Evidence,
    ProducedFile,
    Project,
    ProjectRequest,
    Requirement,
    ToolRegistry,
    VerificationResult,
)
from guacamole.contracts import (
    Decide,
    Deliver,
    Finish,
    Publish,
    PublishedFile,
    Rationale,
    Review,
    ReviewManifest,
    Spawn,
    TaskAuthorization,
    TaskReport,
    ToolCall,
    Verify,
    Wait,
)
from guacamole.decision import DecisionBlocked


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_autonomous_loop_pauses_and_resumes_at_both_human_reviews(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sandbox = root / "outputs"

            def design() -> ProducedFile:
                path = project.output_path(Path("fixture.txt"))
                path.write_text("TEST FIXTURE: not an engineering design")
                return ProducedFile.from_path(path)

            def check(path: str) -> VerificationResult:
                observed = Path(path).read_text().startswith("TEST FIXTURE")
                return VerificationResult(
                    outcome="passed" if observed else "failed",
                    explanation="Fixture file inspected",
                    checks={"fixture": observed},
                )

            tools = ToolRegistry()
            build = tools.register(design)
            validate = tools.register(check)
            grants = (build.definition.grant, validate.definition.grant)

            class Workflow(TestReasoning):
                """The Chief plans and reviews; a worker per stage does the work."""

                def requirements(self):
                    return (
                        Requirement(
                            id="r",
                            wording="fixture",
                            source=project.store.get("source", "brief").ref,
                            source_quote="fixture",
                        ),
                    )

                async def respond(self, packet):
                    assert project.context(packet.id) == packet
                    data = json.loads(packet.prompt)
                    assert data["state"]["sandbox"] == str(sandbox)
                    store = project.store
                    stage = "CDR" if project.reviews.accepted("PDR") else "PDR"
                    requirement = store.maybe("requirement", "r")
                    decisions = [
                        s
                        for s in store.list("decision")
                        if not s.stale
                        and s.data["request"]["kind"] == "work_plan"
                        and s.data["request"]["candidates"][0]["plan"]["stage"] == stage
                    ]
                    artifact = store.maybe("artifact", stage + "-artifact")
                    evidence = store.maybe("evidence", stage + "-evidence")
                    deliverable = store.maybe("deliverable", stage + "-design")
                    artifact = artifact if artifact and not artifact.stale else None
                    evidence = evidence if evidence and not evidence.stale else None
                    deliverable = (
                        deliverable if deliverable and not deliverable.stale else None
                    )
                    if data["agent"]["task_id"] == "chief":
                        workers = [
                            a
                            for a in store.list("agent")
                            if a.data["task_id"] == "work"
                            and decisions
                            and a.data["decision_id"] == decisions[0].ref.id
                        ]
                        if project.reviews.accepted("CDR"):
                            action = Finish(
                                result=TaskReport(
                                    summary="Fixture gates exercised"
                                ).model_dump(mode="json")
                            )
                        elif not decisions:
                            task = TaskAuthorization(
                                id="work", objective="Build and verify", tools=grants
                            )
                            action = Decide(
                                selected="fixture",
                                request=plan_request(
                                    requirement.ref, stage=stage, tasks=(task,)
                                ),
                            )
                        elif not workers:
                            action = Spawn(
                                decision_id=decisions[0].ref.id, task_id="work"
                            )
                        elif deliverable is None:
                            action = Wait(reason="Worker building")
                        else:
                            action = Review(decision_id=decisions[0].ref.id)
                    else:
                        decision = data["agent"]["decision_id"]
                        jobs = [
                            r
                            for r in project.requests(decision=decision)
                            if r.kind == "tool" and r.status == "completed"
                        ]
                        builds = [r for r in jobs if r.target == build.key]
                        checks = [r for r in jobs if r.target == validate.key]
                        if not builds:
                            action = ToolCall(
                                tool=build.definition.grant,
                                arguments={},
                                inputs=(requirement.ref,),
                            )
                        elif artifact is None:
                            action = Publish(
                                files=(
                                    PublishedFile(
                                        path=builds[0].result["path"],
                                        artifact_id=stage + "-artifact",
                                        artifact_kind="editable-design",
                                    ),
                                ),
                                tool_request=builds[0].id,
                                inputs=(requirement.ref,),
                                requirements=(requirement.ref,),
                            )
                        elif not checks:
                            saved = store.model(
                                "artifact", artifact.ref.id, ArtifactRecord
                            )
                            action = ToolCall(
                                tool=validate.definition.grant,
                                arguments={
                                    "path": str(project.verify_file(saved.file))
                                },
                                inputs=(artifact.ref,),
                            )
                        elif evidence is None:
                            result = checks[0].result
                            action = Verify(
                                evidence=Evidence(
                                    id=stage + "-evidence",
                                    kind="verification",
                                    outcome=result["outcome"],
                                    explanation=result["explanation"],
                                    artifacts=(artifact.ref,),
                                    requirements=(requirement.ref,),
                                    request_id=checks[0].id,
                                    decision_id=decision,
                                )
                            )
                        elif deliverable is None:
                            action = Deliver(
                                spec_id=stage + "-design",
                                artifacts=(artifact.ref,),
                                evidence=(evidence.ref,),
                            )
                        else:
                            action = Finish(
                                result=TaskReport(summary="Delivered").model_dump(
                                    mode="json"
                                )
                            )
                    return AgentTurn(
                        rationale=Rationale(
                            objective="Exercise workflow",
                            explanation="Scripted fixture action",
                        ),
                        action=action,
                    )

            with Project(
                root / "state",
                sandbox=sandbox,
                tools=tools,
                reasoning=Workflow(),
            ) as project:
                result = await project.run(
                    ProjectRequest(
                        description="fixture",
                        context=ContextSpec(
                            max_input_tokens=200_000, reserved_output_tokens=1000
                        ),
                    )
                )
                for stage in ("PDR", "CDR"):
                    self.assertEqual(
                        result.status, "awaiting_review", result.model_dump()
                    )
                    ready = next(
                        ref
                        for ref in result.reviews
                        if project.store.resolve(ref).data["stage"] == stage
                    )
                    self.assertTrue(
                        (sandbox / "reviews" / ready.id / "v2/review.md").is_file()
                    )
                    (notice,) = project.human.inbox(run_id=result.run_id)
                    self.assertIn(notice.message.request_id, result.human_requests)
                    with self.assertRaisesRegex(ValueError, "reviews.accept"):
                        project.human.reply(
                            notice.message.request_id, "yes", author="fixture human"
                        )
                    rejected = project.reviews.accept(
                        ready,
                        reviewer="fixture human",
                        accepted=False,
                        disposition=f"Revise the {stage} fixture and resubmit.",
                    )
                    self.assertEqual(
                        project.store.resolve(rejected).data["status"], "rejected"
                    )
                    self.assertFalse(project.human.inbox())
                    with self.assertRaises(ValueError):
                        project.reviews.accept(
                            ready, reviewer="fixture human", disposition="stale"
                        )
                    if stage == "CDR":
                        self.assertTrue(project.reviews.accepted("PDR"))
                    result = await project.run(resume=result.run_id)
                    self.assertEqual(
                        result.status, "awaiting_review", result.model_dump()
                    )
                    ready = next(
                        ref
                        for ref in result.reviews
                        if project.store.resolve(ref).data["stage"] == stage
                    )
                    self.assertNotEqual(ready.id, rejected.id)
                    project.reviews.accept(
                        ready, reviewer="fixture user", disposition="Fixture acceptance"
                    )
                    result = await project.run(resume=result.run_id)
                self.assertEqual(result.status, "complete")
                # The Chief, and a worker per plan: each rejection brought a replan.
                tasks = [s.data["task_id"] for s in project.store.list("agent")]
                self.assertEqual(
                    sorted(tasks), ["chief", "systems_engineer", *["work"] * 4]
                )
                self.assertTrue((sandbox / "work").is_dir())
                self.assertFalse((root / "state/reviews").exists())

    async def test_pdr_cdr_artifact_evidence_human_gate_and_invalidation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def design(value: float) -> ProducedFile:
                """Write an explicitly labelled test fixture, not an engineering design."""
                path = root / "fixture.json"
                path.write_text(json.dumps({"TEST_FIXTURE_ONLY": True, "value": value}))
                return ProducedFile.from_path(path)

            def check(path: str) -> VerificationResult:
                data = json.loads(Path(path).read_text())
                passed = data["value"] == 3048.0
                return VerificationResult(
                    outcome="passed" if passed else "failed",
                    explanation="TEST ONLY: fixture value comparison",
                    # A physical test no program here can run; it still passes.
                    checks={"value": passed, "flight_test": None},
                )

            tools = ToolRegistry()
            generate = tools.register(design)
            verify = tools.register(check)
            grants = (generate.definition.grant, verify.definition.grant)
            with Project(root, tools=tools) as project:
                brief = root / "brief.txt"
                brief.write_text(
                    "10,000ft (+- 2000ft) with active airbrakes and a 3U 2kg payload"
                )
                source = project.ingest(brief, source_id="brief")
                project.store.put(
                    "rationale",
                    "fixture-rationale",
                    Rationale(
                        objective="Test workflow",
                        explanation="These are explicit fixtures, not engineering outputs",
                    ),
                    actor="script",
                )
                requirement = Requirement(
                    id="mission",
                    wording=brief.read_text(),
                    source=source,
                    source_quote=brief.read_text(),
                )
                req_ref = project.record_requirement(requirement)
                await commit_fixture_model(project)
                with self.assertRaises(DecisionBlocked):
                    await project.decisions.choose(
                        plan_request(req_ref, stage="CDR", tools=grants),
                        selected="fixture",
                        explanation="Test fixture selection",
                    )
                accepted_pdr = None
                for stage in ("PDR", "CDR"):
                    decision = await project.decisions.choose(
                        plan_request(req_ref, stage=stage, tools=grants),
                        selected="fixture",
                        explanation="Test fixture selection",
                    )
                    incomplete = await project.reviews.generate(decision)
                    self.assertEqual(
                        project.store.resolve(incomplete).data["status"], "generated"
                    )
                    with self.assertRaises(ValueError):
                        project.reviews.accept(
                            incomplete, reviewer="test human", disposition="premature"
                        )
                    job = project.executor.submit(
                        generate,
                        {"value": 3048.0},
                        decision_id=decision,
                        inputs=(req_ref,),
                    )
                    output = await job.collect()
                    artifact = project.publish(
                        path=output.path,
                        artifact_id=stage + "-artifact",
                        kind="editable-design",
                        request_id=job.id,
                        decision_id=decision,
                        inputs=(req_ref,),
                        requirements=(req_ref,),
                    )
                    # Editing the provider working file cannot alter a published snapshot.
                    Path(output.path).write_text("working file changed")
                    saved = project.store.model("artifact", artifact.id, ArtifactRecord)
                    snapshot_path = project.verify_file(saved.file)
                    check_job = project.executor.submit(
                        verify,
                        {"path": str(snapshot_path)},
                        decision_id=decision,
                        inputs=(artifact,),
                    )
                    verified = await check_job.collect()
                    # Passing evidence about none of a deliverable's artifacts is no proof.
                    unrelated = project.evidence(
                        Evidence(
                            id=stage + "-unrelated",
                            kind="verification",
                            outcome=verified.outcome,
                            explanation=verified.explanation,
                            artifacts=(),
                            requirements=(req_ref,),
                            request_id=check_job.id,
                            decision_id=decision,
                        )
                    )
                    project.deliver(
                        Deliverable(
                            spec_id=stage + "-design",
                            artifacts=(artifact,),
                            evidence=(unrelated,),
                            rationale_id="fixture-rationale",
                        ),
                        decision_id=decision,
                    )
                    self.assertIn(
                        f"{stage}-design: verification evidence covers none of its artifacts",
                        project.reviews.checks(decision)[2],
                    )
                    evidence = project.evidence(
                        Evidence(
                            id=stage + "-evidence",
                            kind="verification",
                            outcome=verified.outcome,
                            explanation=verified.explanation,
                            artifacts=(artifact,),
                            requirements=(req_ref,),
                            request_id=check_job.id,
                            decision_id=decision,
                        )
                    )
                    project.deliver(
                        Deliverable(
                            spec_id=stage + "-design",
                            artifacts=(artifact,),
                            evidence=(evidence,),
                            rationale_id="fixture-rationale",
                        ),
                        decision_id=decision,
                    )
                    ready = await project.reviews.generate(decision)
                    self.assertEqual(
                        project.store.resolve(ready).data["status"], "ready"
                    )
                    self.assertFalse(project.reviews.accepted(stage))
                    accepted = project.reviews.accept(
                        ready,
                        reviewer="test human",
                        disposition="Accept this fixture baseline only",
                    )
                    self.assertTrue(project.reviews.accepted(stage))
                    manifest = project.store.model(
                        "review", accepted.id, ReviewManifest
                    )
                    self.assertIn(artifact, manifest.baseline)
                    # The review document traces each requirement to its evidence.
                    report = (
                        root / "reviews" / accepted.id / "v3/review.md"
                    ).read_text()
                    self.assertIn("| mission |", report)
                    # Its checks are not keyed to the requirement: no pass for it.
                    self.assertIn("| not checked | verification (passed) |", report)
                    self.assertIn("### verification — passed", report)
                    self.assertIn("- verification: flight_test — not performed", report)
                    self.assertTrue(
                        (root / "reviews" / accepted.id / "manifest-v3.json").exists()
                    )
                    if stage == "PDR":
                        accepted_pdr = accepted
                brief.write_text("Changed altitude requirement")
                project.ingest(brief, source_id="brief")
                self.assertTrue(project.store.get("requirement", "mission").stale)
                self.assertFalse(project.reviews.accepted("PDR"))
                self.assertFalse(project.reviews.accepted("CDR"))
                with self.assertRaises(ValueError):
                    project.store.resolve(accepted_pdr, current=True)
                # The revised package says what changed since the accepted baseline:
                # stale work is shown as stale, never carried over as evidence.
                changed = project.record_requirement(
                    requirement.model_copy(
                        update={
                            "wording": "Changed altitude requirement",
                            "source": project.store.get("source", "brief").ref,
                            "source_quote": "Changed altitude requirement",
                        }
                    )
                )
                await commit_fixture_model(project)
                decision = await project.decisions.choose(
                    plan_request(changed, stage="PDR", tools=grants),
                    selected="fixture",
                    explanation="Replan for the changed requirement",
                )
                revised = await project.reviews.generate(decision)
                report = (root / "reviews" / revised.id / "v1/review.md").read_text()
                self.assertIn(
                    f"## Changes since review {accepted_pdr.id} (accepted)", report
                )
                self.assertIn(
                    "| requirement:mission | revision 1 → 2 | 10,000ft (+- 2000ft)",
                    report,
                )
                self.assertIn("| artifact:PDR-artifact | stale |", report)
                self.assertIn(f"| decision:{decision} | added |", report)
                self.assertIn("0 records carry over unchanged", report)


if __name__ == "__main__":
    unittest.main()
