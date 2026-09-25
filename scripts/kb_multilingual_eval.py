"""Cross-lingual retrieval check: English facts, questions in English / Telugu / Hindi / code-mixed.

Uses the configured embedding provider (default Gemini, needs GOOGLE_API_KEY). Reports recall@1/@3 and
similarity for relevant vs unrelated questions, to calibrate KB_MIN_DENSE_SIMILARITY.

    python -m scripts.kb_multilingual_eval
"""
from dotenv import load_dotenv

load_dotenv()

import numpy as np  # noqa: E402

import kb  # noqa: E402
from backend_config import read_config  # noqa: E402

FACTS = {
    "fees": "The total tuition fee for the 6-year MBBS program in Georgia is about 30 lakh rupees, payable yearly.",
    "hostel": "Students stay in university hostels with shared rooms, Wi-Fi, and 24-hour security; Indian food is served in the mess.",
    "eligibility": "To apply you need at least 50 percent in Physics, Chemistry and Biology in Class 12 and a qualifying NEET score.",
    "duration": "The MBBS course lasts six years, including one year of clinical internship.",
    "visa": "We handle the student visa application; processing usually takes three to four weeks after the admission letter.",
    "recognition": "The universities are recognised by the National Medical Commission and listed in the World Directory of Medical Schools.",
    "counselling": "You can book a free counselling session with our advisors from Monday to Saturday, 10 am to 6 pm.",
    "fmge": "Graduates must pass the FMGE / NExT exam to practise in India; we provide coaching during the final years.",
}

QUESTIONS = [
    ("en", "How much is the MBBS fee?", "fees"),
    ("te", "MBBS ఫీజు ఎంత?", "fees"),
    ("hi", "MBBS की फीस कितनी है?", "fees"),
    ("te-en", "Georgia lo MBBS fees entha?", "fees"),
    ("te", "హాస్టల్ లో భోజనం ఎలా ఉంటుంది?", "hostel"),
    ("hi", "हॉस्टल में खाना कैसा मिलता है?", "hostel"),
    ("hi-en", "Hostel mein Indian food milta hai kya?", "hostel"),
    ("te", "అర్హత ఏమిటి? NEET అవసరమా?", "eligibility"),
    ("hi", "एडमिशन के लिए कितने प्रतिशत चाहिए?", "eligibility"),
    ("te", "కోర్సు ఎన్ని సంవత్సరాలు?", "duration"),
    ("hi", "वीज़ा में कितना समय लगता है?", "visa"),
    ("te", "వీసా ఎంత సమయం పడుతుంది?", "visa"),
    ("hi", "क्या यह डिग्री भारत में मान्य है?", "recognition"),
    ("te", "కౌన్సెలింగ్ ఎప్పుడు బుక్ చేసుకోవచ్చు?", "counselling"),
    ("hi", "भारत में प्रैक्टिस के लिए कौन सी परीक्षा देनी होगी?", "fmge"),
]
UNRELATED = [
    ("te", "ఈరోజు వాతావరణం ఎలా ఉంది?"),
    ("hi", "आज क्रिकेट मैच कौन जीता?"),
    ("en", "Can you tell me a joke?"),
    ("hi", "मुझे पिज़्ज़ा ऑर्डर करना है"),
    ("te", "సినిమా టికెట్లు ఎక్కడ దొరుకుతాయి?"),
]


def main() -> None:
    config = read_config()
    runtime = kb.get_runtime_config(config)
    print(f"Provider: {runtime['kb_embedding_provider']} / {runtime['kb_embedding_model']} ({kb.KB_EMBEDDING_DIMENSIONS}d)")
    names = list(FACTS)
    doc_vecs, model = kb.embed_texts([FACTS[n] for n in names], config=config, is_query=False)
    if model.startswith("hashed"):
        raise SystemExit("Embeddings fell back to hashed vectors; set GOOGLE_API_KEY (or a multilingual local model).")
    docs = np.asarray(doc_vecs, dtype=np.float32)

    def rank(question: str) -> list[tuple[str, float]]:
        q, _ = kb.embed_texts([question], config=config, is_query=True)
        sims = docs @ np.asarray(q[0], dtype=np.float32)
        order = np.argsort(-sims)
        return [(names[i], float(sims[i])) for i in order]

    hit1 = hit3 = 0
    relevant_sims: list[float] = []
    print("\nlang   top1          sim    expected")
    for lang, question, expected in QUESTIONS:
        ranking = rank(question)
        top = [n for n, _ in ranking[:3]]
        hit1 += top[0] == expected
        hit3 += expected in top
        relevant_sims.append(dict(ranking)[expected])
        mark = "ok " if top[0] == expected else "MISS"
        print(f"{lang:6} {top[0]:13} {ranking[0][1]:.3f}  {expected:13} {mark}")

    unrelated_max = []
    print("\nunrelated questions (best match similarity):")
    for lang, question in UNRELATED:
        best_name, best_sim = rank(question)[0]
        unrelated_max.append(best_sim)
        print(f"{lang:6} {best_sim:.3f}  ({best_name})  {question}")

    n = len(QUESTIONS)
    print(f"\nrecall@1 {hit1}/{n} = {hit1 / n:.0%}   recall@3 {hit3}/{n} = {hit3 / n:.0%}")
    print(f"relevant similarity: min {min(relevant_sims):.3f}  median {float(np.median(relevant_sims)):.3f}")
    print(f"unrelated best-match similarity: max {max(unrelated_max):.3f}")
    print(f"current KB_MIN_DENSE_SIMILARITY: {runtime['kb_min_dense_similarity']}")


if __name__ == "__main__":
    main()
