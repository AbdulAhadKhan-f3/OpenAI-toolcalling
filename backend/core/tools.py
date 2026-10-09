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
                                "description": "confirmed only when the doctor diagnoses it for this visit; suspected when tentative; ruled_out when excluded; history for past or chronic conditions the patient already had.",
                                "enum": ["confirmed", "suspected", "ruled_out", "history"],
                            },
                            "term": {
                                "type": "string",
                                "description": "short_term for acute or temporary conditions expected to resolve; long_term for chronic, recurring or lifelong conditions.",
                                "enum": ["short_term", "long_term"],
                            },
                            "dx_type": {
                                "type": "string",
                                "description": "The medical category that best fits the condition. Use other only if none of the categories fit.",
                                "enum": ["infectious", "cardiovascular", "respiratory", "metabolic_endocrine", "gastrointestinal",
                                         "neurological", "mental_health", "musculoskeletal", "inflammatory_immune", "injury", "other"],
                            },
                            "note": {"type": "string", "description": "Clarifying context, if needed."},
                            "evidence": {"type": "string", "description": "Exact quote from one transcript sentence."},
                            "speaker": {"type": "string", "enum": ["doctor", "patient", "unclear"], "description": "Who said the evidence sentence. Use unclear if you cannot tell."},
                        },
                        "required": ["name", "status", "term", "dx_type", "evidence", "speaker"],
                    },
                },
            },
            "required": ["diagnoses"],
        },
    },
    {
        "type": "function",
        "name": "extract_medications",
        "description": "Extract prescribed, continued, stopped, or considered medications. Do NOT include allergies here (allergies belong in extract_history under allergy).",
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
                            "route": {"type": "string", "description": "Route of administration, as stated."},
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
        "description": "Extract doctor-stated tests ordered, warning signs and advice.",
        "parameters": {
            "type": "object",
            "properties": {
                "follow_up": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["test_ordered", "warning_sign", "advice"]},
                            "detail": {"type": "string", "description": "What the doctor told the patient to do, as stated."},
                            "timing": {"type": "string", "description": "When it should happen, if stated."},
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
                            "detail": {"type": "string", "description": "The item itself. For an allergy, only the name of the substance, not a sentence."},
                            "duration": {"type": "string", "description": "How long it has lasted, if stated."},
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
                            "detail": {"type": "string", "description": "The measurement or finding, with its value and units as stated."},
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
        "name": "extract_referrals",
        "description": "Extract referrals: the doctor sends the patient to another clinician or service.",
        "parameters": {
            "type": "object",
            "properties": {
                "referrals": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "refer_to": {
                                "type": "string",
                                "description": "The clinician, specialty or service the patient is referred to, as stated."
                            },
                            "detail": {
                                "type": "string",
                                "description": "The reason for the referral, as stated."
                            },
                            "urgency": {
                                "type": "string",
                                "enum": ["routine", "urgent", "emergency"],
                                "description": "Only if the doctor stated how urgent it is."
                            },
                            "condition": {
                                "type": "string",
                                "description": "If the referral only applies when something happens, that condition as stated."
                            },
                            "evidence": {
                                "type": "string",
                                "description": "Exact quote from one transcript sentence."
                            },
                            "speaker": {
                                "type": "string",
                                "enum": ["doctor", "patient", "unclear"],
                                "description": "Who said the evidence sentence. Use unclear if you cannot tell."
                            }
                        },
                        "required": ["refer_to", "detail", "evidence", "speaker"]
                    }
                }
            },
            "required": ["referrals"]
        }
    },
    {
        "type": "function",
        "name": "extract_recalls",
        "description": "Extract recalls: the doctor wants the patient to return later for a review or a repeat test.",
        "parameters": {
            "type": "object",
            "properties": {
                "recalls": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "detail": {
                                "type": "string",
                                "description": "What the recall is for, as stated."
                            },
                            "type": {
                                "type": "string",
                                "enum": ["review_visit", "repeat_test", "other"],
                                "description": "The type of recall."
                            },
                            "due": {
                                "type": "string",
                                "description": "When the patient should return, as stated (an interval or a date)."
                            },
                            "evidence": {
                                "type": "string",
                                "description": "Exact quote from one transcript sentence."
                            },
                            "speaker": {
                                "type": "string",
                                "enum": ["doctor", "patient", "unclear"],
                                "description": "Who said the evidence sentence. Use unclear if you cannot tell."
                            }
                        },
                        "required": ["detail", "type", "evidence", "speaker"]
                    }
                }
            },
            "required": ["recalls"]
        }
    },
    {
        "type": "function",
        "name": "extract_tasks",
        "description": "Extract tasks: actions that someone must carry out after the visit and that are not a referral, a recall, a test order, a warning sign or advice.",
        "parameters": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "detail": {
                                "type": "string",
                                "description": "The action to carry out, as stated."
                            },
                            "owner": {
                                "type": "string",
                                "enum": ["doctor", "clinic_staff", "patient", "unclear"],
                                "description": "Who must do it. Use unclear if it is not stated."
                            },
                            "due": {
                                "type": "string",
                                "description": "When it should be done, as stated."
                            },
                            "evidence": {
                                "type": "string",
                                "description": "Exact quote from one transcript sentence."
                            },
                            "speaker": {
                                "type": "string",
                                "enum": ["doctor", "patient", "unclear"],
                                "description": "Who said the evidence sentence. Use unclear if you cannot tell."
                            }
                        },
                        "required": ["detail", "owner", "evidence", "speaker"]
                    }
                }
            },
            "required": ["tasks"]
        }
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
