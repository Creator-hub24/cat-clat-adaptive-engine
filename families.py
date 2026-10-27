"""Exam families: one codebase, one Streamlit app per family, selected by the EXAM_FAMILY secret/env.

Each family has its own sections, branding and its own Pro (tracked per family in public.pro_entitlements).
No Streamlit import here so it stays unit-testable.
"""
from __future__ import annotations

import os

DEFAULT_FAMILY = "mgmt_law"

FAMILIES: dict[str, dict] = {
    "mgmt_law": {
        "name": "CAT/CLAT Adaptive Engine",
        "title": "CAT/CLAT Adaptive Mock Test & Analytics Engine",
        "sidebar_title": "🎯 Adaptive Engine",
        "tagline": "Questions built like a faculty member builds them: every wrong option is a named trap.",
        "icon": "🎯",
        "badge": "🔥",
        "accent": None,  # None = no injected CSS: keeps the current (default) look exactly
        "accent2": None,
        "sections": {
            "CAT": ["CAT Quant", "CAT VARC RC", "CAT DILR"],
            "CLAT": ["CLAT RC", "CLAT Logical Reasoning", "CLAT Legal Reasoning", "CLAT Current Affairs & GK"],
            "IPMAT": ["IPMAT Quant", "IPMAT Verbal"],
        },
        "level_labels": {},
        "coming_soon": False,
    },
    "sarkari": {
        "name": "Sarkari Exam Adaptive Engine",
        "title": "SSC · Railway · Bank Adaptive Practice Engine",
        "sidebar_title": "🏛️ Sarkari Exam Engine",
        "tagline": "SSC CGL/CHSL, Railway NTPC/Group D and Bank IBPS/SBI PO/Clerk: verified questions, "
                   "named traps, speed tracking.",
        "icon": "🏛️",
        "badge": "🏛️",
        "accent": "#138808",   # India green
        "accent2": "#FF9933",  # saffron
        "sections": {
            "SSC · Railway · Bank": ["Sarkari Quantitative Aptitude", "Sarkari Reasoning", "Sarkari English",
                                     "Sarkari General Awareness"],
        },
        "level_labels": {"CAT-Level": "Exam-Level"},
        "coming_soon": False,
    },
    "medical": {
        "name": "NEET Adaptive Engine",
        "title": "NEET UG Adaptive Practice Engine",
        "sidebar_title": "🩺 NEET Engine",
        "tagline": "NEET UG practice built on NCERT. Coming soon.",
        "icon": "🩺",
        "badge": "🩺",
        "accent": "#0F9D8F",   # teal
        "accent2": "#14B8A6",
        "sections": {"NEET UG": []},  # placeholder: no question content yet
        "level_labels": {"CAT-Level": "Exam-Level"},
        "coming_soon": True,
    },
    "engineering": {
        "name": "JEE Adaptive Engine",
        "title": "JEE Main Adaptive Practice Engine",
        "sidebar_title": "⚙️ JEE Engine",
        "tagline": "JEE Main Physics, Chemistry and Maths practice. Coming soon.",
        "icon": "⚙️",
        "badge": "⚙️",
        "accent": "#1E63D6",   # blue
        "accent2": "#3B82F6",
        "sections": {"JEE Main": []},  # placeholder: no question content yet
        "level_labels": {"CAT-Level": "Exam-Level"},
        "coming_soon": True,
    },
}


def resolve_family(value: str | None = None) -> str:
    """Normalise a family key; empty/unknown falls back to the default (current app behaviour)."""
    key = str(value if value is not None else os.environ.get("EXAM_FAMILY", "")).strip().lower()
    return key if key in FAMILIES else DEFAULT_FAMILY


def get_family(value: str | None = None) -> dict:
    key = resolve_family(value)
    return {"key": key, **FAMILIES[key]}


def family_topics(family: dict | str) -> set[str]:
    fam = get_family(family) if isinstance(family, str) else family
    return {t for sec in fam["sections"].values() for t in sec}


def topic_family(topic: str) -> str | None:
    for key, fam in FAMILIES.items():
        if topic in family_topics(key):
            return key
    return None


def theme_css(family: dict) -> str:
    """CSS for accent colours, or '' for families that keep the default theme (mgmt_law)."""
    a, b = family.get("accent"), family.get("accent2") or family.get("accent")
    if not a:
        return ""
    return f"""<style>
:root {{ --primary-color: {a}; }}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {{
  background-color: {a}; border-color: {a}; color: #fff; }}
.stButton > button[kind="primary"]:hover {{ background-color: {b}; border-color: {b}; }}
.stButton > button:hover, .stLinkButton > a:hover {{ border-color: {a}; color: {a}; }}
[data-testid="stSidebar"] {{ border-top: 6px solid {b}; }}
[data-testid="stAppViewContainer"] h1 {{ border-bottom: 4px solid {a}; padding-bottom: .25rem; }}
div[role="radiogroup"] label:has(input:checked) div:first-child {{ background-color: {a} !important; }}
</style>"""
