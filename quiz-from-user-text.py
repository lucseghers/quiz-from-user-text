# quiz-from-user-text.py (Aangepast van quiz-from-youtube.py)

import os
import json
import copy
import uuid
import tempfile
from pathlib import Path
from zipfile import ZipFile

import streamlit as st
from openai import OpenAI


# ---------- Helper: OpenAI client (Gebruikt Caching voor snelheid) ----------
@st.cache_resource 
def get_openai_client(api_key: str) -> OpenAI:
    """
    Cache de OpenAI client, zodat deze niet bij elke Streamlit herlading opnieuw wordt gemaakt.
    """
    return OpenAI(api_key=api_key)


# ---------- NIEUWE FUNCTIE: Geplakte tekst converteren naar JSON MC-vragen ----------

def clean_and_parse_questions(
    raw_text: str,
    question_language: str = "Nederlands",
    client: OpenAI = None,
):
    """
    Gebruikt GPT-4o om een willekeurig geformatteerde tekst met vragen
    om te zetten naar de vereiste JSON-structuur voor H5P.
    """
    
    prompt = f"""
Je krijgt een tekst die meerkeuzevragen bevat in een willekeurig formaat.
Het kunnen opsommingen, bullet points, of gewoon geplakte tekst zijn.
Jouw taak is om deze tekst te analyseren en er een lijst van **volledige meerkeuzevragen** van te maken.

Regels:
- Vertaal niet; geef de vragen en antwoorden exact terug zoals ze in de invoertekst staan, in het {question_language}.
- Elke vraag moet 4 antwoordmogelijkheden hebben en 1 correcte index.
- Geef ALLEEN geldig JSON terug in dit exacte formaat:

{{
  "questions": [
    {{
      "question": "vraagtekst",
      "answers": ["antwoord A", "antwoord B", "antwoord C", "antwoord D"],
      "correct_index": 0 
    }}
  ]
}}

Ongeformatteerde invoertekst:
\"\"\"{raw_text}\"\"\"    
"""

    response = client.chat.completions.create(
        model="gpt-4o", 
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "Je bent een JSON-validator en tekstanalyseur. Je extracteert meerkeuzevragen uit ongeformatteerde tekst en geeft ze altijd terug als geldige JSON in het gespecificeerde formaat.",
            },
            {"role": "user", "content": prompt},
        ],
    )

    raw = response.choices[0].message.content
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError("Model antwoordde geen geldige JSON (kon niet parsen).")

    return data.get("questions", [])


# ---------- H5P helpers (ONGEWIJZIGD) ----------
def build_questions_from_mc(mc_questions, template_content):
    """
    Zet je eigen mc_questions om naar H5P.MultiChoice vragen,
    met behoud van de instellingen (feedback, knoppen, gedrag)
    uit de eerste vraag van de template.
    """
    base_q = template_content["questions"][0]  # eerste vraag als sjabloon
    base_params = base_q["params"]

    new_questions = []
    for i, q in enumerate(mc_questions, start=1):
        q_obj = copy.deepcopy(base_q)
        params = q_obj["params"]

        # Vraagtekst
        params["question"] = q["question"]

        # Antwoorden
        answers = []
        correct_idx = q.get("correct_index", 0) # Gebruik .get() met fallback voor extra veiligheid
        for idx, ans in enumerate(q["answers"]):
            ans_obj = copy.deepcopy(base_params["answers"][0])
            ans_obj["text"] = ans
            ans_obj["correct"] = bool(idx == correct_idx)
            answers.append(ans_obj)
        params["answers"] = answers

        # Metadata / ID
        q_obj["metadata"]["title"] = f"Vraag {i}"
        q_obj["metadata"]["extraTitle"] = f"Vraag {i}"
        q_obj["subContentId"] = str(uuid.uuid4())

        new_questions.append(q_obj)

    return new_questions


def create_h5p_from_template(template_h5p_path, output_h5p_path, mc_questions):
    """
    - Leest quiz-template.h5p
    - Vervangt de vragen door mc_questions
    - Schrijft een nieuw H5P-bestand weg.
    """
    template_h5p_path = Path(template_h5p_path)
    output_h5p_path = Path(output_h5p_path)

    with ZipFile(template_h5p_path, "r") as zin:
        # content.json inlezen
        content_json = json.loads(
            zin.read("content/content.json").decode("utf-8")
        )

        # vragen vervangen
        content_json["questions"] = build_questions_from_mc(
            mc_questions, content_json
        )

        new_content_bytes = json.dumps(
            content_json, ensure_ascii=False, indent=2
        ).encode("utf-8")

        # nieuwe .h5p schrijven
        with ZipFile(output_h5p_path, "w") as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "content/content.json":
                    data = new_content_bytes
                zout.writestr(item, data)


# ---------- Streamlit UI (AANGEPAST) ----------
st.set_page_config(page_title="Tekst → H5P-quiz", page_icon="📝")

st.title("📝 Tekst → 📚 H5P meerkeuzequiz (Robuuste Modus)")

# Optioneel: logo bovenaan tonen
logo_path = "logo.png"
if os.path.exists(logo_path):
    st.image(logo_path, width=400)
else:
    st.warning(f"Logo '{logo_path}' niet gevonden.")


st.markdown(
    """
1. **Haal de Vragen op:** Gebruik een tool (zoals ChatGPT of Gemini) om een YouTube-video te analyseren en daar meerkeuzevragen uit te genereren.
"""
)

# AANGEPASTE WEERGAVE VAN DE PROMPT
voorbeeld_prompt = """
Kan je onderstaande video even samenvatten en daar dan 5 MC vragen over weergeven.
Geef enkel de MC vragen als output.
Gebruik de taal van de video.
Geef het juiste antwoord duidelijk aan.
Video: [PLAK HIER DE YOUTUBE URL]
"""

# st.code zorgt voor een gekaderd blok met kopieerknop
st.code(voorbeeld_prompt, language='markdown') 

st.markdown(
    """
2. **Plak de Vragen:** Plak de gecreëerde vragen (in willekeurig formaat) in het tekstveld hieronder.
3. **Genereer & Download:** De app converteert de tekst automatisch naar het juiste H5P-formaat.
"""
)
# API-key: Gebruik st.secrets, met fallback naar invoerveld
try:
    api_key = st.secrets["OPENAI_API_KEY"]
    st.info("OpenAI API-sleutel is geladen vanuit Streamlit secrets. ✅")
except (KeyError, AttributeError):
    # Fallback: Als de key niet in secrets staat, vraag er dan om
    api_key = st.text_input(
        "OpenAI API-sleutel",
        type="password",
        help="Deze sleutel is nodig om de geplakte tekst om te zetten naar gestructureerde JSON.",
    )
    if api_key:
        st.warning("Handmatige sleutel ingevoerd. Let op: beter om `st.secrets` te gebruiken.")

# NIEUWE INVOER: Tekst met vragen
raw_questions_text = st.text_area(
    "Plak hier de meerkeuzevragen (bijv. gekopieerd uit ChatGPT/Gemini):",
    height=300,
    placeholder="1. Wat is de hoofdstad van België?\nA. Brussel (Juist)\nB. Parijs\nC. Berlijn\n(De AI zal dit formaat analyseren)",
)

# Taalkeuze
taal_opties = [
    "Nederlands",
    "Engels",
    "Frans",
    "Duits",
    "Spaans",
    "Italiaans",
]
taal_vragen = st.selectbox(
    "Taal waarin de geplakte vragen staan", options=taal_opties, index=0
)

# H5P template upload of default
st.markdown("#### H5P-template")
uploaded_template = st.file_uploader(
    "Upload een H5P-template (bv. quiz-template.h5p). "
    "Laat leeg om `quiz-template.h5p` uit deze map te gebruiken.",
    type="h5p",
)

if st.button("🚀 Converteer naar H5P-quiz"):
    if not api_key:
        st.error("Vul eerst je OpenAI API-sleutel in, of stel deze in via Streamlit secrets.")
    elif not raw_questions_text.strip():
        st.error("Plak eerst de meerkeuzevragen in het tekstveld.")
    else:
        try:
            client = get_openai_client(api_key)

            with tempfile.TemporaryDirectory() as tmpdir_str:
                tmpdir = Path(tmpdir_str)

                with st.status("Bezig met verwerken...", expanded=True) as status:
                    
                    # 1️⃣ Vragen analyseren en structureren
                    status.write("1️⃣ Vragen analyseren en structureren via OpenAI GPT-4o...")
                    mc_questions = clean_and_parse_questions(
                        raw_questions_text,
                        question_language=taal_vragen,
                        client=client,
                    )
                    
                    if not mc_questions:
                        status.update(label="Analyse Mislukt ❌", state="error")
                        st.error("""
                        De analyse is mislukt! De AI kon geen gestructureerde meerkeuzevragen
                        vinden in de geplakte tekst.
                        
                        **Tips:** Zorg dat elke vraag duidelijk de vraag, de 4 antwoorden, 
                        en het juiste antwoord (of de index/letter) bevat.
                        """)
                        st.stop()
                        
                    status.write(f"✅ {len(mc_questions)} gestructureerde vragen ontvangen.")

                    # 2️⃣ H5P opbouwen
                    status.write("2️⃣ H5P-bestand opbouwen...")

                    # Template bepalen (upload of standaard)
                    if uploaded_template is not None:
                        template_path = tmpdir / "template.h5p"
                        template_path.write_bytes(uploaded_template.read())
                    else:
                        template_path = Path("quiz-template.h5p")
                        if not template_path.exists():
                            raise FileNotFoundError(
                                "quiz-template.h5p niet gevonden in de huidige map "
                                "en er is geen template geüpload."
                            )

                    output_name = f"quiz-from-text-{uuid.uuid4().hex[:8]}.h5p"
                    output_path = tmpdir / output_name

                    create_h5p_from_template(template_path, output_path, mc_questions)
                    status.write(f"✅ H5P-quiz aangemaakt: {output_name}")

                    status.update(label="Klaar! ✅", state="complete", expanded=False)

                # Vragen tonen
                st.markdown("### Voorbeeld van de geconverteerde vragen")
                for i, q in enumerate(mc_questions, start=1):
                    with st.expander(f"Vraag {i}"):
                        st.write(q["question"])
                        correct_index = q.get("correct_index", -1) # Haal de index op
                        for idx, ans in enumerate(q["answers"]):
                            label = chr(ord("A") + idx)
                            # Markeer het juiste antwoord in de expando
                            prefix = "✅ " if idx == correct_index else "- "
                            st.write(f"{prefix}**{label}.** {ans}")
                        if correct_index == -1:
                             st.warning("⚠️ Juiste antwoord niet correct aangegeven in JSON.")


                # Downloadknop
                file_bytes = output_path.read_bytes()
                st.download_button(
                    "⬇️ Download H5P-quiz",
                    data=file_bytes,
                    file_name=output_name,
                    mime="application/zip",
                )

        except Exception as e:
            st.error(f"Er ging iets mis: {e}")