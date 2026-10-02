"""Controlled typed checkpoint records used by boundary tests."""


def typed_intent_answers(answers):
    for item in answers:
        if item["section"] == "Information, investigation and remaining uncertainty":
            item["evidence"] = [{
                "question": "Which repository control owns the value?",
                "source": "Observed pom.xml",
                "finding": "The property owns the value in the controlled fixture.",
                "uncertainty": "Runtime compatibility requires execution checks.",
            }]
        elif item["section"] == "Concrete candidate solutions":
            item["candidates"] = [{
                "id": "A", "name": "Change the owning property",
                "solution": "Update the observed owner and validate the result.",
                "evidence": "The fixture repository declares this owner.",
                "constraints": "The change stays within the authorized source scope.",
                "validation": "Run configured checks and independent validation.",
                "classification": "COMPLETE",
            }]
        elif item["section"] == "Selected solution":
            item["selection"] = {
                "candidate_id": "A", "rationale": "The observed owner is the coherent control point.",
                "challenge": "No other supported control point remains in the fixture; reconsider on contrary evidence.",
            }
    return answers
