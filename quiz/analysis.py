"""تحليل محاولة تلميذ: المستوى، النجاح حسب الصعوبة والمحور، مؤشرات الإجابة العشوائية، والتوصيات.

التقرير متاح بالعربية (ar) وبالفرنسية (fr)؛ الفرنسية لكل المواد ما عدا العربية.
"""
from collections import Counter, OrderedDict
from statistics import median

from .topics import ADVICE, ADVICE_FR, DEFAULT_TOPIC, DEFAULT_TOPIC_FR, guess_topic

LEVEL_CODES = ["E", "M", "H"]

# (الحد الأدنى للنسبة المئوية، رمز التقدير، لون)
GRADES = [(80, "vg", "ok"), (65, "g", "ok"), (50, "p", "warn"), (30, "w", "ko"), (0, "n", "ko")]

MSG = {
    "ar": {
        "levels": {"E": "بسيطة", "M": "متوسطة", "H": "صعبة"},
        "level_short": {"E": "بسيط", "M": "متوسط", "H": "صعب"},
        "grades": {"vg": "جيد جدًا", "g": "جيد", "p": "لا بأس به", "w": "ضعيف", "n": "بلا مستوى"},
        "summary": {
            "vg": "مستوى ممتاز، يتقن أغلب محاور المادة.",
            "g": "مستوى جيد، مع بعض النقاط التي تحتاج إلى مراجعة.",
            "p": "مستوى مقبول، لكن عنده نقائص واضحة في بعض المحاور.",
            "w": "مستوى ضعيف، يحتاج إلى مراجعة جادة ومتابعة.",
            "n": "لم يُظهر تحكمًا في المادة؛ يحتاج إلى إعادة بناء الأساسيات مع متابعة قريبة.",
        },
        "verdict": {"ko": "إجاباته عشوائية على الأرجح", "warn": "في إجاباته جزء من التخمين",
                    "ok": "إجاباته مدروسة وليست عشوائية"},
        "ind_chance": "عدد إجاباته الصحيحة ({c} من {n}) قريب مما يحصل عليه من يجيب عشوائيًا (حوالي {e} إجابة صحيحة بالصدفة).",
        "ind_levels": "لم ينجح في الأسئلة البسيطة أكثر من المتوسطة، والمعتاد أن يكون البسيط أسهل عليه؛ "
                      "هذا يدل على أن اختياره لم يكن مبنيًا على الفهم.",
        "ind_letter": "اختار الحرف {l} في {c} سؤالًا من {n} ({p}%)، بينما الإجابات الصحيحة موزعة بالتساوي تقريبًا على A وB وC وD.",
        "ind_run": "أجاب بنفس الحرف في {k} أسئلة متتالية.",
        "ind_fast": "أجاب بسرعة كبيرة: حوالي {s} ثوانٍ بين السؤال والآخر في المتوسط، وهي مدة لا تكفي لقراءة السؤال وحله.",
        "ind_fast2": "أنهى الامتحان في {m} دقيقة فقط لـ {n} سؤال، أي أقل من 10 ثوانٍ للسؤال.",
        "rec_random": "الأولوية الأولى: ترك الإجابة العشوائية. عليه أن يقرأ كل سؤال بتمعّن، ويستبعد الخيارات الخاطئة "
                      "واحدًا واحدًا، ولا يختار إلا بعد التفكير. الإجابة العشوائية لا تعكس مستواه الحقيقي.",
        "rec_guess": "التقليل من التخمين: أن يأخذ وقته في قراءة السؤال، ويحل على المسودة، ويستبعد الخيارات غير الممكنة قبل الاختيار.",
        "rec_fast": "استغلال وقت الامتحان كاملًا ومراجعة الإجابات قبل التسليم بدل الإسراع.",
        "rec_basics": "عنده نقص في الأساسيات: يجب أن يبدأ بمراجعة الدروس الأساسية وحل التمارين البسيطة في الكتاب المدرسي "
                      "حتى يتقنها، قبل الانتقال إلى التمارين الأصعب.",
        "rec_medium": "يتقن الأساسيات، لكنه يحتاج إلى التدرب على تمارين تطبيقية متعددة الخطوات (المستوى المتوسط).",
        "rec_hard": "مستواه جيد في البسيط والمتوسط؛ ليتقدم أكثر يحتاج إلى تمارين التعمق والمسائل المركبة.",
        "rec_topic": "محور «{t}» (نجح في {c} من {n}): {tip}",
        "rec_topic_default": "مراجعة هذا الدرس في الكتاب المدرسي وحل تمارينه.",
        "rec_unanswered": "ترك {k} سؤالًا بدون إجابة: عليه تنظيم الوقت، والبدء بالأسئلة التي يعرفها ثم الرجوع إلى الباقي.",
        "rec_violations": "سُجّلت له {k} محاولة خروج من صفحة الامتحان؛ يجب تنبيهه إلى الالتزام بقواعد الامتحان.",
        "rec_ok": "نتيجته جيدة ومتوازنة؛ يُنصح بالمحافظة على المراجعة المنتظمة وحل تمارين إضافية للتعمق.",
    },
    "fr": {
        "levels": {"E": "faciles", "M": "moyennes", "H": "difficiles"},
        "level_short": {"E": "Facile", "M": "Moyen", "H": "Difficile"},
        "grades": {"vg": "Très bien", "g": "Bien", "p": "Passable", "w": "Faible", "n": "Sans niveau"},
        "summary": {
            "vg": "Excellent niveau : l'élève maîtrise la plupart des notions de la matière.",
            "g": "Bon niveau, avec quelques points à revoir.",
            "p": "Niveau acceptable, mais avec des lacunes nettes dans certaines notions.",
            "w": "Niveau faible : une révision sérieuse et un suivi sont nécessaires.",
            "n": "L'élève ne maîtrise pas la matière ; il faut reconstruire les bases avec un suivi rapproché.",
        },
        "verdict": {"ko": "Réponses probablement données au hasard", "warn": "Une partie des réponses a été devinée",
                    "ok": "Réponses réfléchies, non aléatoires"},
        "ind_chance": "Son nombre de bonnes réponses ({c} sur {n}) est proche de celui obtenu en répondant au hasard "
                      "(environ {e} bonnes réponses par chance).",
        "ind_levels": "Il n'a pas mieux réussi les questions faciles que les questions moyennes, alors que les faciles "
                      "devraient l'être davantage : ses choix ne reposaient pas sur la compréhension.",
        "ind_letter": "Il a choisi la lettre {l} dans {c} questions sur {n} ({p} %), alors que les bonnes réponses sont "
                      "réparties à peu près également entre A, B, C et D.",
        "ind_run": "Il a donné la même lettre à {k} questions consécutives.",
        "ind_fast": "Il a répondu très vite : environ {s} secondes entre deux questions en moyenne, ce qui ne suffit pas "
                    "pour lire et résoudre une question.",
        "ind_fast2": "Il a terminé l'examen en {m} minutes seulement pour {n} questions, soit moins de 10 secondes par question.",
        "rec_random": "Priorité absolue : arrêter de répondre au hasard. Lire chaque question attentivement, éliminer les "
                      "mauvaises réponses une par une et ne choisir qu'après réflexion. Les réponses au hasard ne "
                      "reflètent pas son vrai niveau.",
        "rec_guess": "Deviner moins : prendre le temps de lire la question, chercher au brouillon et éliminer les choix "
                     "impossibles avant de répondre.",
        "rec_fast": "Utiliser tout le temps de l'examen et relire ses réponses avant de rendre la copie au lieu de se précipiter.",
        "rec_basics": "Lacunes dans les notions de base : il doit d'abord revoir les leçons fondamentales et refaire les "
                      "exercices simples du manuel jusqu'à les maîtriser, avant de passer aux exercices plus difficiles.",
        "rec_medium": "Il maîtrise les bases, mais doit s'entraîner sur des exercices d'application en plusieurs étapes "
                      "(niveau moyen).",
        "rec_hard": "Bon niveau aux questions faciles et moyennes ; pour progresser, il lui faut des exercices "
                    "d'approfondissement et des problèmes complexes.",
        "rec_topic": "« {t} » ({c} bonne(s) réponse(s) sur {n}) : {tip}",
        "rec_topic_default": "Revoir cette leçon dans le manuel et refaire ses exercices.",
        "rec_unanswered": "{k} questions sans réponse : il doit mieux gérer son temps, commencer par les questions qu'il "
                          "sait traiter puis revenir aux autres.",
        "rec_violations": "{k} tentative(s) de sortie de la page d'examen enregistrée(s) : il faut lui rappeler les règles de l'examen.",
        "rec_ok": "Résultat bon et équilibré : continuer à réviser régulièrement et faire des exercices supplémentaires "
                  "d'approfondissement.",
    },
}

# عناوين صفحة التقرير
LABELS = {
    "ar": {
        "title": "تقرير التلميذ", "print": "طباعة التقرير", "back": "رجوع للنتائج", "submitted": "سلّم في",
        "duration": "المدة", "minutes": "دقيقة", "score": "النقطة", "correct": "إجابات صحيحة",
        "unanswered": "بدون إجابة", "violations": "محاولات الخروج", "of": "من",
        "s1": "1. التقييم العام", "s2": "2. النتيجة حسب صعوبة الأسئلة", "s3": "3. النتيجة حسب المحاور",
        "s4": "4. هل كانت إجاباته عشوائية؟", "s5": "5. التوصيات: على ماذا يركز وماذا يفعل",
        "s6": "6. الأسئلة التي أخطأ فيها أو تركها", "questions": "الأسئلة", "strong": "نقاط القوة",
        "weak": "مواطن الضعف", "no_indicator": "لم يظهر أي مؤشر على الإجابة العشوائية: نتيجته أعلى بوضوح مما يحصل "
        "عليه من يجيب بالصدفة (حوالي {e} إجابة صحيحة)، وإجاباته متوازنة.",
        "col_num": "رقم السؤال (عنده)", "col_topic": "المحور", "col_level": "الصعوبة", "col_answer": "إجابته",
        "col_right": "الصحيحة", "no_answer": "بدون إجابة",
    },
    "fr": {
        "title": "Rapport de l'élève", "print": "Imprimer le rapport", "back": "Retour aux résultats",
        "submitted": "Remis le", "duration": "Durée", "minutes": "min", "score": "Note",
        "correct": "Bonnes réponses", "unanswered": "Sans réponse", "violations": "Tentatives de sortie", "of": "sur",
        "s1": "1. Appréciation générale", "s2": "2. Résultats selon la difficulté des questions",
        "s3": "3. Résultats par notion", "s4": "4. A-t-il répondu au hasard ?",
        "s5": "5. Recommandations : sur quoi se concentrer et que faire",
        "s6": "6. Questions ratées ou laissées sans réponse", "questions": "Questions", "strong": "Points forts",
        "weak": "Points faibles", "no_indicator": "Aucun indice de réponses au hasard : son résultat est nettement "
        "supérieur à celui obtenu par chance (environ {e} bonnes réponses) et ses réponses sont cohérentes.",
        "col_num": "N° de la question (pour lui)", "col_topic": "Notion", "col_level": "Difficulté",
        "col_answer": "Sa réponse", "col_right": "Bonne réponse", "no_answer": "Sans réponse",
    },
}


SUBJECTS_FR = {"الرياضيات": "Mathématiques", "الفيزياء والكيمياء": "Physique-chimie",
               "العلوم الطبيعية": "Sciences naturelles", "الفرنسية": "Français", "العربية": "Arabe"}
ADMISSION_TITLE = "امتحان القبول في مدارس المعارف الحرة"


def exam_label(exam, lang):
    """عنوان الامتحان واسم المادة بلغة التقرير."""
    if lang != "fr":
        return exam.title, exam.subject.name
    subject = SUBJECTS_FR.get(exam.subject.name, exam.subject.name)
    title = exam.title
    if title.startswith(ADMISSION_TITLE):
        title = f"Examen d'admission aux écoles El Maarif Libres – {subject}"
    return title, subject


def _pct(a, b):
    return round(100 * a / b) if b else None


def _prob_at_least(k, probs):
    """احتمال أن يصيب من يجيب عشوائيًا k سؤالًا على الأقل (لكل سؤال احتمال خاص)."""
    dist = [1.0]
    for p in probs:
        new = [0.0] * (len(dist) + 1)
        for i, v in enumerate(dist):
            new[i] += v * (1 - p)
            new[i + 1] += v * p
        dist = new
    return sum(dist[k:])


def grade_label(pct, lang="ar"):
    for threshold, code, css in GRADES:
        if pct >= threshold:
            return MSG[lang]["grades"][code], css, code
    code, css = GRADES[-1][1], GRADES[-1][2]
    return MSG[lang]["grades"][code], css, code


def report_languages(exam):
    """لغات التقرير المتاحة: الفرنسية لكل المواد ما عدا العربية."""
    return ["ar"] if exam.subject.name == "العربية" else ["ar", "fr"]


def analyze(attempt, lang="ar"):
    exam = attempt.exam
    if lang not in report_languages(exam):
        lang = "ar"
    m = MSG[lang]
    advice = ADVICE_FR if lang == "fr" else ADVICE
    subject = exam.subject.name
    questions = {q.id: q for q in attempt.graded_questions().prefetch_related("choices")}
    order = [qid for qid in (attempt.question_order or []) if qid in questions] or list(questions)
    answers = {a.question_id: a for a in attempt.answers.all()}

    rows = []
    for pos, qid in enumerate(order, 1):
        q = questions[qid]
        a = answers.get(qid)
        sel = (a.selected if a else "").upper()
        n_choices = q.choices.count() or 4
        rows.append({
            "pos": pos, "q": q, "selected": sel, "answered": bool(sel),
            "correct": bool(sel) and sel == q.correct_answer.upper(),
            "level": q.level, "level_name": m["level_short"].get(q.level, "—"),
            "topic": q.topic or guess_topic(subject, q.text, [c.text for c in q.choices.all()]),
            "p_random": 1 / n_choices, "time": a.answered_at if a else None,
            "changes": a.changes if a else 0,
        })

    n = len(rows)
    n_answered = sum(r["answered"] for r in rows)
    n_correct = sum(r["correct"] for r in rows)
    total = float(attempt.total or sum(float(r["q"].points) for r in rows) or 1)
    score = float(attempt.score)
    pct = round(100 * score / total) if total else 0
    grade, grade_css, grade_code = grade_label(pct, lang)

    # حسب الصعوبة
    by_level = []
    for code in LEVEL_CODES:
        rs = [r for r in rows if r["level"] == code]
        if rs:
            c = sum(r["correct"] for r in rs)
            by_level.append({"code": code, "name": m["levels"][code], "n": len(rs), "correct": c,
                             "pct": _pct(c, len(rs))})
    lvl = {b["code"]: b["pct"] for b in by_level}

    # حسب المحور
    topics = OrderedDict()
    for r in rows:
        t = topics.setdefault(r["topic"], {"topic": r["topic"], "n": 0, "correct": 0})
        t["n"] += 1
        t["correct"] += r["correct"]
    by_topic = sorted(topics.values(), key=lambda t: (t["correct"] / t["n"], -t["n"]))
    for t in by_topic:
        t["pct"] = _pct(t["correct"], t["n"])
    weak = [t for t in by_topic if t["pct"] < 50 and (t["n"] >= 2 or t["pct"] == 0)
            and t["topic"] not in (DEFAULT_TOPIC, DEFAULT_TOPIC_FR)]
    strong = [t for t in reversed(by_topic) if t["pct"] >= 80 and t["n"] >= 2]

    # ---- مؤشرات الإجابة العشوائية ----
    indicators = []
    expected = sum(r["p_random"] for r in rows)
    p_chance = _prob_at_least(n_correct, [r["p_random"] for r in rows]) if n else 1
    chance_like = p_chance >= 0.05
    if chance_like:
        indicators.append(m["ind_chance"].format(c=n_correct, n=n, e=f"{expected:.0f}"))
    if all(lvl.get(k) is not None for k in LEVEL_CODES):
        if lvl["E"] <= lvl["M"] + 5 and lvl["E"] < 60:
            indicators.append(m["ind_levels"])
    letters = Counter(r["selected"] for r in rows if r["answered"])
    if n_answered >= 10:
        letter, cnt = letters.most_common(1)[0]
        if cnt / n_answered >= 0.5:
            indicators.append(m["ind_letter"].format(l=letter, c=cnt, n=n_answered, p=_pct(cnt, n_answered)))
    run, best = 1, 1
    for prev, cur in zip(rows, rows[1:]):
        run = run + 1 if cur["answered"] and cur["selected"] == prev["selected"] else 1
        best = max(best, run)
    if best >= 6:
        indicators.append(m["ind_run"].format(k=best))

    times = sorted(r["time"] for r in rows if r["time"])
    duration_min = None
    if attempt.submitted_at:
        duration_min = round((attempt.submitted_at - attempt.started_at).total_seconds() / 60)
    fast = False
    if len(times) >= 10:
        gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
        med = median(gaps)
        if med < 8:
            fast = True
            indicators.append(m["ind_fast"].format(s=f"{med:.0f}"))
    elif duration_min is not None and n and duration_min * 60 / n < 10 and n_answered >= n / 2:
        fast = True
        indicators.append(m["ind_fast2"].format(m=duration_min, n=n))

    if chance_like and (len(indicators) >= 2 or p_chance >= 0.3):
        verdict_css = "ko"
    elif chance_like or len(indicators) >= 2 or fast:
        verdict_css = "warn"
    else:
        verdict_css = "ok"
    verdict = m["verdict"][verdict_css]

    # ---- التوصيات ----
    recs = []
    if verdict_css == "ko":
        recs.append(m["rec_random"])
    elif verdict_css == "warn":
        recs.append(m["rec_guess"])
    if fast:
        recs.append(m["rec_fast"])
    if lvl.get("E") is not None and lvl["E"] < 60:
        recs.append(m["rec_basics"])
    elif lvl.get("M") is not None and lvl["M"] < 50:
        recs.append(m["rec_medium"])
    elif lvl.get("H") is not None and lvl["H"] < 34 and pct >= 65:
        recs.append(m["rec_hard"])
    for t in weak[:5]:
        tip = advice.get(t["topic"], m["rec_topic_default"])
        recs.append(m["rec_topic"].format(t=t["topic"], c=t["correct"], n=t["n"], tip=tip))
    unanswered = n - n_answered
    if n and unanswered / n > 0.1:
        recs.append(m["rec_unanswered"].format(k=unanswered))
    if attempt.violations:
        recs.append(m["rec_violations"].format(k=attempt.violations))
    if not recs:
        recs.append(m["rec_ok"])

    labels = dict(LABELS[lang])
    labels["no_indicator"] = labels["no_indicator"].format(e=round(expected, 1))
    wrong = [r for r in rows if not r["correct"]]
    return {
        "lang": lang, "dir": "ltr" if lang == "fr" else "rtl", "L": labels,
        "exam_title": exam_label(exam, lang)[0], "subject": exam_label(exam, lang)[1],
        "languages": report_languages(exam),
        "attempt": attempt, "exam": exam, "n": n, "n_answered": n_answered, "n_correct": n_correct,
        "unanswered": unanswered, "score": score, "total": total, "pct": pct,
        "grade": grade, "grade_css": grade_css, "summary": m["summary"][grade_code],
        "by_level": by_level, "by_topic": by_topic, "weak": weak, "strong": strong,
        "verdict": verdict, "verdict_css": verdict_css, "indicators": indicators,
        "p_chance": round(100 * p_chance), "expected": round(expected, 1),
        "duration_min": duration_min, "recs": recs, "wrong": wrong,
    }
