import hashlib

from guacamole.websocket import control

# True: accept the package; the benchmark finishes this brief and starts the next.
# False: request changes; the text goes to the Chief as a correction and the
# benchmark holds again at the next ready review.
accepted = True
disposition = """
Accepted for PDR.
"""

with control(8767, "bracket benchmark") as send:
    # The review's human request carries the exact review revision to answer.
    inbox = send({"kind": "human_inbox"})["inbox"]
    reviews = [
        ref
        for entry in inbox
        for ref in entry["message"]["payload"].get("references", [])
        if ref["kind"] == "review"
    ]
    if not reviews:
        raise SystemExit("No review is waiting for a disposition.")
    review = reviews[0]
    print(f"Answering review {review['id']} revision {review['revision']}", flush=True)
    send(
        {
            "kind": "review_disposition",
            "review": review,
            "reviewer": "Khoi",
            "disposition": disposition,
            "accepted": accepted,
        },
        # The ID follows the review and text: rerunning returns the stored result
        # instead of answering twice, and an edited disposition is always sent.
        id="review-"
        + hashlib.sha256(
            f"{review['sha256']}{accepted}{disposition}".encode()
        ).hexdigest()[:12],
    )
