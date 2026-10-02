"""OpenAI Responses API tool schemas exposed to the model."""

TOOLS = [
    {
        "type": "function",
        "name": "extract_diagnoses",
        "description": "Extract diagnoses and conditions with confirmed, suspected, ruled-out, or history status.",
        "parameters": {
            "type": "object",
            "properties": {
                "diagnoses": {
                    "type": "array",
                    "description": "Every diagnosis or medical condition discussed, with its final status.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Diagnosis or condition name."},
                            "status": {
                                "type": "string",
                                "description": "confirmed only when the doctor diagnoses it for this visit; suspected when tentative; ruled_out when excluded; history for past or chronic conditions.",
                                "enum": ["confirmed", "suspected", "ruled_out", "history"],
                            },
                            "note": {"type": "string", "description": "Clarifying context, if needed."},
                            "evidence": {"type": "string", "description": "Exact quote from one transcript sentence."},
                            "speaker": {"type": "string", "enum": ["doctor", "patient", "unclear"], "description": "Who said the evidence sentence. Use unclear if you cannot tell."},
                        },
                        "required": ["name", "status", "note", "evidence", "speaker"],
                    },
                },
            },
            "required": ["diagnoses"],
        },
    },
    {
        "type": "function",
        "name": "extract_medications",
        "description": "Extract mentioned medications, their status, and prescription details.",
        "parameters": {
            "type": "object",
            "properties": {
                "medications": {
                    "type": "array",
                    "description": "Every medication mentioned, with its final status and any stated details.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Medication name."},
                            "status": {
                                "type": "string",
                                "enum": ["prescribed", "dose_changed", "continued", "stopped", "not_prescribed", "patient_reported"],
                            },
                            "dose": {"type": "string", "description": "Dose as stated, including units."},
                            "route": {"type": "string", "description": "Route, such as oral or intravenous."},
                            "frequency": {"type": "string", "description": "How often to take it."},
                            "timing": {"type": "string", "description": "When to take it, if stated."},
                            "duration": {"type": "string", "description": "Course duration, if stated."},
                            "start": {"type": "string", "description": "Start time or date, if stated."},
                            "end": {"type": "string", "description": "End time or date, if stated."},
                            "indication": {"type": "string", "description": "Reason for taking it, if stated."},
                            "reason": {"type": "string", "description": "Reason for change, stop, or avoidance."},
                            "instructions": {"type": "string", "description": "Other doctor-stated instructions."},
                            "evidence": {"type": "string", "description": "Exact quote from one transcript sentence."},
                            "speaker": {"type": "string", "enum": ["doctor", "patient", "unclear"], "description": "Who said the evidence sentence. Use unclear if you cannot tell."},
                        },
                        "required": ["name", "status", "evidence", "speaker"],
                    },
                },
            },
            "required": ["medications"],
        },
    },
    {
        "type": "function",
        "name": "extract_follow_up",
        "description": "Extract doctor-stated follow-up, referrals, tests, advice, and warning signs.",
        "parameters": {
            "type": "object",
            "properties": {
                "follow_up": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["follow_up_visit", "referral", "test_ordered", "warning_sign", "advice"]},
                            "detail": {"type": "string"},
                            "timing": {"type": "string"},
                            "evidence": {"type": "string", "description": "Exact quote from one doctor sentence."},
                            "speaker": {"type": "string", "enum": ["doctor", "patient", "unclear"], "description": "Who said the evidence sentence. Use unclear if you cannot tell."},
                        },
                        "required": ["type", "detail", "evidence", "speaker"],
                    },
                },
            },
            "required": ["follow_up"],
        },
    },
    {
        "type": "function",
        "name": "extract_history",
        "description": "Extract the chief complaint, symptoms, allergies, and medical, family, and social history.",
        "parameters": {
            "type": "object",
            "properties": {
                "history": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {"type": "string", "enum": ["chief_complaint", "symptom", "allergy", "past_history", "family_history", "social_history"]},
                            "detail": {"type": "string"},
                            "duration": {"type": "string"},
                            "evidence": {"type": "string", "description": "Exact quote from one transcript sentence."},
                            "speaker": {"type": "string", "enum": ["doctor", "patient", "unclear"], "description": "Who said the evidence sentence. Use unclear if you cannot tell."},
                        },
                        "required": ["category", "detail", "evidence", "speaker"],
                    },
                },
            },
            "required": ["history"],
        },
    },
    {
        "type": "function",
        "name": "extract_findings",
        "description": "Extract vital signs, examination findings, and test results.",
        "parameters": {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {"type": "string", "enum": ["vital_sign", "exam", "test_result"]},
                            "detail": {"type": "string"},
                            "evidence": {"type": "string", "description": "Exact quote from one transcript sentence."},
                            "speaker": {"type": "string", "enum": ["doctor", "patient", "unclear"], "description": "Who said the evidence sentence. Use unclear if you cannot tell."},
                        },
                        "required": ["category", "detail", "evidence", "speaker"],
                    },
                },
            },
            "required": ["findings"],
        },
    },
    {
        "type": "function",
        "name": "generate_soap_note",
        "description": "Generate the SOAP note and summary after all extraction tools have run.",
        "parameters": {
            "type": "object",
            "properties": {
                "subjective": {"type": "string", "description": "Chief complaint, symptoms, allergies, and history."},
                "objective": {"type": "string", "description": "Measurements, examination, and test results."},
                "assessment": {"type": "string", "description": "Diagnoses and their status."},
                "plan": {"type": "string", "description": "Stated medications, changes, follow-up, referrals, and advice."},
                "summary": {"type": "string", "description": "Brief summary of the encounter."},
            },
            "required": ["subjective", "objective", "assessment", "plan", "summary"],
        },
    },
]