"""
Service layer for the Legal Consultant chat feature.

Handles OpenAI API calls, system prompt construction, jurisdiction profiles,
mentor mode, confidence scoring, and title generation.
"""

try:
    import openai as _openai_module
    _OPENAI_AVAILABLE = True
except ImportError:
    _openai_module = None
    _OPENAI_AVAILABLE = False

from app.database import get_integration_setting, db_conn

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUBJECT_AREAS = [
    "labor", "civil", "commercial", "criminal", "family",
    "administrative", "tax", "constitutional", "immigration", "environmental",
]

CONSULTATION_TYPES = [
    "general", "case_analysis", "document_review", "regulatory_check",
]

CONFIDENCE_LABELS = {
    (0.8, 1.0): ("high", "emerald"),
    (0.5, 0.8): ("medium", "amber"),
    (0.0, 0.5): ("low", "rose"),
}

# ---------------------------------------------------------------------------
# Jurisdiction Profiles
# ---------------------------------------------------------------------------

DEFAULT_JURISDICTIONS = [
    {
        "name": "panama",
        "display_name": "Panamá",
        "flag_emoji": "🇵🇦",
        "system_prompt_extra": (
            "Key legal framework: Código Civil (1916), Código de Comercio, Código Judicial, "
            "Código de Trabajo (1972), Ley 16 de 1990 (Arbitraje), Constitución Política de 1972. "
            "Court structure: Corte Suprema de Justicia, Tribunales Superiores, Juzgados de Circuito, "
            "Juzgados Municipales. Panama uses a civil law system."
        ),
        "key_laws": "Código Civil, Código de Comercio, Código Judicial, Código de Trabajo, Constitución 1972",
        "court_structure": "Corte Suprema → Tribunales Superiores → Juzgados de Circuito → Juzgados Municipales",
    },
    {
        "name": "costa_rica",
        "display_name": "Costa Rica",
        "flag_emoji": "🇨🇷",
        "system_prompt_extra": (
            "Key legal framework: Constitución Política (1949), Código Civil, Código de Trabajo, "
            "Código Procesal Civil, Código Penal, Ley de Jurisdicción Constitucional. "
            "Court structure: Corte Suprema de Justicia (Salas I-IV), Tribunales de Apelación, "
            "Juzgados de Primera Instancia. Costa Rica uses a civil law system with strong constitutional protections."
        ),
        "key_laws": "Constitución 1949, Código Civil, Código de Trabajo, Código Procesal Civil, Código Penal",
        "court_structure": "Corte Suprema (4 Salas) → Tribunales de Apelación → Juzgados de Primera Instancia",
    },
    {
        "name": "colombia",
        "display_name": "Colombia",
        "flag_emoji": "🇨🇴",
        "system_prompt_extra": (
            "Key legal framework: Constitución Política (1991), Código Civil, Código General del Proceso, "
            "Código Sustantivo del Trabajo, Código Penal (Ley 599/2000), Código de Comercio. "
            "Court structure: Corte Constitucional, Corte Suprema de Justicia, Consejo de Estado, "
            "Tribunales Superiores, Juzgados. Colombia has acción de tutela for fundamental rights protection."
        ),
        "key_laws": "Constitución 1991, Código Civil, CGP, CST, Código Penal Ley 599/2000, Código de Comercio",
        "court_structure": "Corte Constitucional / Corte Suprema / Consejo de Estado → Tribunales → Juzgados",
    },
]


def seed_jurisdiction_profiles():
    """Insert default jurisdiction profiles if they don't exist."""
    with db_conn() as conn:
        for jp in DEFAULT_JURISDICTIONS:
            existing = conn.execute(
                "SELECT id FROM jurisdiction_profiles WHERE name = ?", (jp["name"],)
            ).fetchone()
            if not existing:
                conn.execute("""
                    INSERT INTO jurisdiction_profiles
                        (name, display_name, flag_emoji, system_prompt_extra, key_laws, court_structure)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (jp["name"], jp["display_name"], jp["flag_emoji"],
                      jp["system_prompt_extra"], jp["key_laws"], jp["court_structure"]))


def get_jurisdiction_profiles() -> list[dict]:
    """Return all jurisdiction profiles."""
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM jurisdiction_profiles ORDER BY display_name"
        ).fetchall()
    return [dict(r) for r in rows]


def get_jurisdiction_by_name(name: str) -> dict | None:
    """Return a jurisdiction profile by name or display_name."""
    if not name:
        return None
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM jurisdiction_profiles WHERE name = ? OR display_name = ?",
            (name, name)
        ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# OpenAI helpers
# ---------------------------------------------------------------------------

def get_openai_api_key() -> str | None:
    """Return the stored OpenAI API key or None."""
    return get_integration_setting("openai_api_key") or None


def build_legal_system_prompt(
    jurisdiction: str | None = None,
    subject_area: str | None = None,
    mentor_mode: bool = False,
) -> str:
    """Build a system prompt for the legal assistant with jurisdiction context."""
    base = (
        "You are a professional legal research assistant embedded in a law-office "
        "management platform. Your role is to help lawyers and legal staff analyze "
        "legal questions, review documents, and research applicable laws.\n\n"
        "Guidelines:\n"
        "- Be precise and cite specific articles, laws, or regulations when possible.\n"
        "- Clearly distinguish between established legal principles and your interpretation.\n"
        "- When the answer is uncertain, say so explicitly.\n"
        "- Never fabricate case numbers, resolution numbers, or citations.\n"
        "- Always recommend verification with qualified counsel for actionable decisions.\n"
        "- Use the same language the user writes in.\n"
        "- Structure longer answers with clear sections and bullet points.\n"
    )

    # Mentor mode: explain reasoning and cite teaching references
    if mentor_mode:
        base += (
            "\n**MENTOR MODE ACTIVE**: In addition to answering, teach the user. "
            "Explain your legal reasoning step-by-step. Cite relevant doctrinal sources, "
            "textbooks, and foundational principles. When appropriate, pose follow-up "
            "questions to help the user deepen their understanding.\n"
        )

    # Subject area context
    if subject_area:
        base += f"\nFocus area: **{subject_area.replace('_', ' ').title()}** law.\n"

    # Jurisdiction profile
    if jurisdiction:
        jp = get_jurisdiction_by_name(jurisdiction)
        if jp and jp.get("system_prompt_extra"):
            base += f"\n**Jurisdiction: {jp['display_name']}**\n{jp['system_prompt_extra']}\n"
        else:
            base += (
                f"\nThe user is consulting about the jurisdiction of **{jurisdiction}**. "
                f"Focus your analysis on the laws and legal framework of {jurisdiction}. "
                f"If you reference laws from other jurisdictions for comparison, label them clearly.\n"
            )

    # Confidence signal instruction
    base += (
        "\n\nAt the END of every response, add a confidence line in this exact format:\n"
        "CONFIDENCE: [high|medium|low]\n"
        "- high = well-established legal principle with clear citations\n"
        "- medium = reasonable interpretation but may vary\n"
        "- low = uncertain, speculative, or jurisdiction-dependent\n"
    )

    return base


def _extract_confidence(text: str) -> tuple[str, float]:
    """Extract confidence level from the response and return (clean_text, score)."""
    lines = text.strip().split("\n")
    confidence = 0.5  # default medium

    for i in range(len(lines) - 1, max(len(lines) - 5, -1), -1):
        line = lines[i].strip().upper()
        if "CONFIDENCE:" in line:
            if "HIGH" in line:
                confidence = 0.9
            elif "LOW" in line:
                confidence = 0.3
            else:
                confidence = 0.6
            # Remove the confidence line from visible text
            lines.pop(i)
            break

    return "\n".join(lines).strip(), confidence


def generate_legal_response(
    messages: list[dict],
    jurisdiction: str | None = None,
    subject_area: str | None = None,
    mentor_mode: bool = False,
) -> tuple[str, float]:
    """
    Call OpenAI and return (reply_text, confidence_score).

    Raises ValueError if the API key is missing.
    Raises RuntimeError on API errors.
    """
    if not _OPENAI_AVAILABLE:
        raise RuntimeError(
            "The OpenAI library is not installed on this server. "
            "The Legal Consultant feature is currently unavailable."
        )

    api_key = get_openai_api_key()
    if not api_key:
        raise ValueError("OpenAI API key is not configured.")

    system_msg = {
        "role": "system",
        "content": build_legal_system_prompt(jurisdiction, subject_area, mentor_mode),
    }
    full_messages = [system_msg] + messages

    try:
        client = _openai_module.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=full_messages,
            max_tokens=2048,
            temperature=0.3,
        )
        raw_reply = response.choices[0].message.content or ""
        clean_text, confidence = _extract_confidence(raw_reply)
        return clean_text, confidence
    except _openai_module.AuthenticationError:
        raise RuntimeError("Invalid OpenAI API key. Please check your Settings.")
    except _openai_module.RateLimitError:
        raise RuntimeError("OpenAI rate limit reached. Please try again in a moment.")
    except _openai_module.APIError as exc:
        raise RuntimeError(f"OpenAI API error: {exc}")
    except Exception as exc:
        raise RuntimeError(f"Unexpected error calling OpenAI: {exc}")


def get_confidence_label(score: float) -> tuple[str, str]:
    """Return (label, color) for a confidence score."""
    for (lo, hi), (label, color) in CONFIDENCE_LABELS.items():
        if lo <= score <= hi:
            return label, color
    return "medium", "amber"


def summarize_title(text: str) -> str:
    """Generate a short conversation title from the first user message."""
    clean = text.strip().replace("\n", " ")
    if len(clean) <= 60:
        return clean
    return clean[:57] + "..."


# ---------------------------------------------------------------------------
# Case Studies
# ---------------------------------------------------------------------------

def save_case_study(user_id: int, conversation_id: int | None, title: str,
                    jurisdiction: str | None, subject_area: str | None,
                    summary: str, outcome: str | None, lessons: str | None) -> int:
    """Save a conversation as a case study. Returns the case study id."""
    with db_conn() as conn:
        cur = conn.execute("""
            INSERT INTO legal_case_studies
                (conversation_id, user_id, title, jurisdiction, subject_area,
                 summary, outcome, lessons_learned)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (conversation_id, user_id, title, jurisdiction, subject_area,
              summary, outcome, lessons))
    return cur.lastrowid


def get_case_studies(user_id: int | None = None) -> list[dict]:
    """Return case studies, optionally filtered by user."""
    with db_conn() as conn:
        if user_id:
            rows = conn.execute("""
                SELECT cs.*, u.full_name as author_name
                FROM legal_case_studies cs
                LEFT JOIN users u ON u.id = cs.user_id
                WHERE cs.user_id = ?
                ORDER BY cs.created_at DESC
            """, (user_id,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT cs.*, u.full_name as author_name
                FROM legal_case_studies cs
                LEFT JOIN users u ON u.id = cs.user_id
                ORDER BY cs.created_at DESC
            """).fetchall()
    return [dict(r) for r in rows]


def validate_case_study(case_study_id: int, validator_user_id: int) -> bool:
    """Mark a case study as peer-validated."""
    with db_conn() as conn:
        conn.execute("""
            UPDATE legal_case_studies
            SET is_peer_validated = 1, validated_by_user_id = ?, validated_at = datetime('now')
            WHERE id = ?
        """, (validator_user_id, case_study_id))
    return True
