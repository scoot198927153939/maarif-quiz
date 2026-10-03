"""تحليل محاولة تلميذ: المستوى، النجاح حسب الصعوبة والمحور، مؤشرات الإجابة العشوائية، والتوصيات."""
from collections import Counter, OrderedDict
from statistics import median

from .topics import ADVICE, ADVICE_FR, DEFAULT_TOPIC, DEFAULT_TOPIC_FR, guess_topic

LEVELS = OrderedDict([("E", "بسيطة"), ("M", "متوسطة"), ("H", "صعبة")])
LEVELS_FR = {"E": "Questions faciles", "M": "Questions moyennes", "H": "Questions difficiles"}
GRADES_FR = {"جيد جدًا": "Très bien", "جيد": "Bien", "لا بأس به": "Assez bien", "ضعيف": "Faible",
             "بلا مستوى": "Sans niveau"}

# (الحد الأدنى للنسبة المئوية، التقدير، لون)
GRADES = [
    (80, "جيد جدًا", "ok"),
    (65, "جيد", "ok"),
    (50, "لا بأس به", "warn"),
    (30, "ضعيف", "ko"),
    (0, "بلا مستوى", "ko"),
]


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


def grade_label(pct):
    for threshold, label, css in GRADES:
        if pct >= threshold:
            return label, css
    return GRADES[-1][1], GRADES[-1][2]


LABELS = {
    "ar": {
        "title": "تقرير التلميذ", "submitted": "سلّم في", "duration": "المدة", "minutes": "دقيقة",
        "score": "النقطة", "correct": "إجابات صحيحة", "of": "من", "unanswered": "بدون إجابة",
        "violations": "محاولات الخروج", "s1": "1. التقييم العام", "s2": "2. النتيجة حسب صعوبة الأسئلة",
        "s3": "3. النتيجة حسب المحاور", "strong": "نقاط القوة", "weak": "مواطن الضعف",
        "s4": "4. هل كانت إجاباته عشوائية؟",
        "no_ind": "لم يظهر أي مؤشر على الإجابة العشوائية: نتيجته أعلى بوضوح مما يحصل عليه من يجيب بالصدفة "
                  "(حوالي {} إجابة صحيحة)، وإجاباته متوازنة.",
        "s5": "5. التوصيات: على ماذا يركز وماذا يفعل", "s6": "6. الأسئلة التي أخطأ فيها أو تركها",
        "qnum": "رقم السؤال (عنده)", "topic": "المحور", "level": "الصعوبة", "his": "إجابته", "right": "الصحيحة",
        "E": "بسيط", "M": "متوسط", "H": "صعب", "sep": "، ",
    },
    "fr": {
        "title": "Rapport de l'élève", "submitted": "Rendu le", "duration": "Durée", "minutes": "min",
        "score": "Note", "correct": "bonnes réponses", "of": "sur", "unanswered": "sans réponse",
        "violations": "sorties de page", "s1": "1. Appréciation générale", "s2": "2. Résultats selon la difficulté",
        "s3": "3. Résultats par thème", "strong": "Points forts", "weak": "Points faibles",
        "s4": "4. A-t-il répondu au hasard ?",
        "no_ind": "Aucun signe de réponses au hasard : son résultat est nettement supérieur à celui d'un élève "
                  "répondant par chance (environ {} bonnes réponses) et ses réponses sont équilibrées.",
        "s5": "5. Recommandations : sur quoi se concentrer et que faire",
        "s6": "6. Questions ratées ou laissées sans réponse",
        "qnum": "N° de la question (chez lui)", "topic": "Thème", "level": "Difficulté", "his": "Sa réponse",
        "right": "Bonne réponse", "E": "Facile", "M": "Moyen", "H": "Difficile", "sep": ", ",
    },
}


SUBJECTS_FR = {"الرياضيات": "Mathématiques", "الفيزياء والكيمياء": "Physique-chimie",
               "العلوم الطبيعية": "Sciences naturelles", "الفرنسية": "Français"}


def report_languages(exam):
    """التقرير بالفرنسية متاح لكل المواد ماعدا العربية."""
    return ["ar"] if exam.subject.name == "العربية" else ["ar", "fr"]


def analyze(attempt, lang="ar"):
    exam = attempt.exam
    if lang not in report_languages(exam):
        lang = "ar"
    fr = lang == "fr"

    def t(ar, fr_text):
        return fr_text if fr else ar
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
            "level": q.level, "topic": q.topic or guess_topic(subject, q.text, [c.text for c in q.choices.all()]),
            "p_random": 1 / n_choices, "time": a.answered_at if a else None,
            "changes": a.changes if a else 0,
        })

    n = len(rows)
    n_answered = sum(r["answered"] for r in rows)
    n_correct = sum(r["correct"] for r in rows)
    total = float(attempt.total or sum(float(r["q"].points) for r in rows) or 1)
    score = float(attempt.score)
    pct = round(100 * score / total) if total else 0
    grade, grade_css = grade_label(pct)
    grade_ar = grade
    if fr:
        grade = GRADES_FR[grade]

    # حسب الصعوبة
    by_level = []
    for code, name in LEVELS.items():
        rs = [r for r in rows if r["level"] == code]
        if rs:
            c = sum(r["correct"] for r in rs)
            by_level.append({"code": code, "name": name, "label": t(f"الأسئلة ال{name}", LEVELS_FR[code]),
                             "n": len(rs), "correct": c, "pct": _pct(c, len(rs))})
    lvl = {b["code"]: b["pct"] for b in by_level}

    # حسب المحور
    topics = OrderedDict()
    for r in rows:
        tp = topics.setdefault(r["topic"], {"topic": r["topic"], "n": 0, "correct": 0})
        tp["n"] += 1
        tp["correct"] += r["correct"]
    by_topic = sorted(topics.values(), key=lambda tp: (tp["correct"] / tp["n"], -tp["n"]))
    for tp in by_topic:
        tp["pct"] = _pct(tp["correct"], tp["n"])
    weak = [tp for tp in by_topic if tp["pct"] < 50 and (tp["n"] >= 2 or tp["pct"] == 0) and tp["topic"] not in (DEFAULT_TOPIC, DEFAULT_TOPIC_FR)]
    strong = [tp for tp in reversed(by_topic) if tp["pct"] >= 80 and tp["n"] >= 2]

    # ---- مؤشرات الإجابة العشوائية ----
    indicators = []
    expected = sum(r["p_random"] for r in rows)
    p_chance = _prob_at_least(n_correct, [r["p_random"] for r in rows]) if n else 1
    chance_like = p_chance >= 0.05
    if chance_like:
        indicators.append(t(
            f"عدد إجاباته الصحيحة ({n_correct} من {n}) قريب مما يحصل عليه من يجيب عشوائيًا "
            f"(حوالي {expected:.0f} إجابة صحيحة بالصدفة).",
            f"Son nombre de bonnes réponses ({n_correct} sur {n}) est proche de celui qu'obtiendrait "
            f"un élève répondant au hasard (environ {expected:.0f} bonnes réponses par chance)."))
    if "E" in lvl and "H" in lvl and lvl["E"] is not None and lvl["H"] is not None and "M" in lvl:
        if lvl["E"] <= lvl["M"] + 5 and lvl["E"] < 60:
            indicators.append(t(
                "لم ينجح في الأسئلة البسيطة أكثر من المتوسطة، والمعتاد أن يكون البسيط أسهل عليه؛ "
                "هذا يدل على أن اختياره لم يكن مبنيًا على الفهم.",
                "Il ne réussit pas mieux les questions faciles que les moyennes, alors que les faciles "
                "devraient lui être plus accessibles : ses choix ne reposent pas sur la compréhension."))
    letters = Counter(r["selected"] for r in rows if r["answered"])
    if n_answered >= 10:
        letter, cnt = letters.most_common(1)[0]
        if cnt / n_answered >= 0.5:
            indicators.append(t(
                f"اختار الحرف {letter} في {cnt} سؤالًا من {n_answered} ({_pct(cnt, n_answered)}%)، "
                "بينما الإجابات الصحيحة موزعة بالتساوي تقريبًا على A وB وC وD.",
                f"Il a choisi la lettre {letter} dans {cnt} questions sur {n_answered} ({_pct(cnt, n_answered)} %), "
                "alors que les bonnes réponses sont réparties à peu près également entre A, B, C et D."))
    run, best = 1, 1
    for prev, cur in zip(rows, rows[1:]):
        run = run + 1 if cur["answered"] and cur["selected"] == prev["selected"] else 1
        best = max(best, run)
    if best >= 6:
        indicators.append(t(f"أجاب بنفس الحرف في {best} أسئلة متتالية.",
                            f"Il a donné la même lettre à {best} questions consécutives."))

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
            indicators.append(t(
                f"أجاب بسرعة كبيرة: حوالي {med:.0f} ثوانٍ بين السؤال والآخر في المتوسط، "
                "وهي مدة لا تكفي لقراءة السؤال وحله.",
                f"Il a répondu très vite : environ {med:.0f} secondes entre deux questions en moyenne, "
                "ce qui ne suffit pas pour lire et résoudre une question."))
    elif duration_min is not None and n and duration_min * 60 / n < 10 and n_answered >= n / 2:
        fast = True
        indicators.append(t(f"أنهى الامتحان في {duration_min} دقيقة فقط لـ {n} سؤال، أي أقل من 10 ثوانٍ للسؤال.",
                            f"Il a terminé l'examen en {duration_min} minutes seulement pour {n} questions, "
                            "soit moins de 10 secondes par question."))

    if chance_like and (len(indicators) >= 2 or p_chance >= 0.3):
        verdict, verdict_css = t("إجاباته عشوائية على الأرجح", "Réponses très probablement au hasard"), "ko"
    elif chance_like or len(indicators) >= 2 or fast:
        verdict, verdict_css = t("في إجاباته جزء من التخمين", "Une partie des réponses est devinée"), "warn"
    else:
        verdict, verdict_css = t("إجاباته مدروسة وليست عشوائية", "Réponses réfléchies, pas au hasard"), "ok"

    # ---- التوصيات ----
    recs = []
    if verdict_css == "ko":
        recs.append(t(
            "الأولوية الأولى: ترك الإجابة العشوائية. عليه أن يقرأ كل سؤال بتمعّن، ويستبعد الخيارات الخاطئة "
            "واحدًا واحدًا، ولا يختار إلا بعد التفكير. الإجابة العشوائية لا تعكس مستواه الحقيقي.",
            "Priorité absolue : arrêter de répondre au hasard. Il doit lire chaque question attentivement, "
            "éliminer les mauvais choix un par un et ne choisir qu'après réflexion. Les réponses au hasard "
            "ne reflètent pas son vrai niveau."))
    elif verdict_css == "warn":
        recs.append(t(
            "التقليل من التخمين: أن يأخذ وقته في قراءة السؤال، ويحل على المسودة، ويستبعد الخيارات غير الممكنة قبل الاختيار.",
            "Deviner moins : prendre le temps de lire la question, la résoudre au brouillon et éliminer "
            "les choix impossibles avant de répondre."))
    if fast:
        recs.append(t("استغلال وقت الامتحان كاملًا (ساعة و45 دقيقة) ومراجعة الإجابات قبل التسليم بدل الإسراع.",
                      "Utiliser tout le temps de l'examen (1 h 45) et relire ses réponses avant de rendre, "
                      "au lieu de se précipiter."))
    if lvl.get("E") is not None and lvl["E"] < 60:
        recs.append(t(
            "عنده نقص في الأساسيات: يجب أن يبدأ بمراجعة الدروس الأساسية وحل التمارين البسيطة في الكتاب المدرسي "
            "حتى يتقنها، قبل الانتقال إلى التمارين الأصعب.",
            "Lacunes dans les bases : il doit d'abord revoir les leçons essentielles et faire les exercices "
            "simples du manuel jusqu'à les maîtriser, avant de passer aux exercices plus difficiles."))
    elif lvl.get("M") is not None and lvl["M"] < 50:
        recs.append(t("يتقن الأساسيات، لكنه يحتاج إلى التدرب على تمارين تطبيقية متعددة الخطوات (المستوى المتوسط).",
                      "Il maîtrise les bases mais doit s'entraîner sur des exercices d'application "
                      "à plusieurs étapes (niveau moyen)."))
    elif lvl.get("H") is not None and lvl["H"] < 34 and pct >= 65:
        recs.append(t("مستواه جيد في البسيط والمتوسط؛ ليتقدم أكثر يحتاج إلى تمارين التعمق والمسائل المركبة.",
                      "Bon niveau sur les questions faciles et moyennes ; pour progresser, il lui faut "
                      "des exercices d'approfondissement et des problèmes complexes."))
    for w in weak[:5]:
        if fr:
            tip = ADVICE_FR.get(w["topic"], "Revoir cette leçon dans le manuel et refaire ses exercices.")
            recs.append(f"Thème « {w['topic']} » ({w['correct']} réussie(s) sur {w['n']}) : {tip}")
        else:
            tip = ADVICE.get(w["topic"], "مراجعة هذا الدرس في الكتاب المدرسي وحل تمارينه.")
            recs.append(f"محور «{w['topic']}» (نجح في {w['correct']} من {w['n']}): {tip}")
    unanswered = n - n_answered
    if n and unanswered / n > 0.1:
        recs.append(t(f"ترك {unanswered} سؤالًا بدون إجابة: عليه تنظيم الوقت، والبدء بالأسئلة التي يعرفها ثم الرجوع إلى الباقي.",
                      f"{unanswered} question(s) sans réponse : il doit mieux gérer son temps, commencer par "
                      "les questions qu'il sait faire puis revenir aux autres."))
    if attempt.violations:
        recs.append(t(f"سُجّلت له {attempt.violations} محاولة خروج من صفحة الامتحان؛ يجب تنبيهه إلى الالتزام بقواعد الامتحان.",
                      f"{attempt.violations} tentative(s) de sortie de la page d'examen enregistrée(s) : "
                      "il faut lui rappeler de respecter les règles de l'examen."))
    if not recs:
        recs.append(t("نتيجته جيدة ومتوازنة؛ يُنصح بالمحافظة على المراجعة المنتظمة وحل تمارين إضافية للتعمق.",
                      "Résultat bon et équilibré ; il est conseillé de continuer à réviser régulièrement "
                      "et de faire des exercices supplémentaires d'approfondissement."))

    summary = {
        "جيد جدًا": "مستوى ممتاز، يتقن أغلب محاور المادة.",
        "جيد": "مستوى جيد، مع بعض النقاط التي تحتاج إلى مراجعة.",
        "لا بأس به": "مستوى مقبول، لكن عنده نقائص واضحة في بعض المحاور.",
        "ضعيف": "مستوى ضعيف، يحتاج إلى مراجعة جادة ومتابعة.",
        "بلا مستوى": "لم يُظهر تحكمًا في المادة؛ يحتاج إلى إعادة بناء الأساسيات مع متابعة قريبة.",
    }[grade_ar]
    if fr:
        summary = {
            "جيد جدًا": "Excellent niveau : il maîtrise la plupart des thèmes de la matière.",
            "جيد": "Bon niveau, avec quelques points à revoir.",
            "لا بأس به": "Niveau acceptable, mais avec des lacunes nettes dans certains thèmes.",
            "ضعيف": "Niveau faible : il a besoin d'une révision sérieuse et d'un suivi.",
            "بلا مستوى": "Il n'a pas montré de maîtrise de la matière ; il faut reconstruire les bases avec un suivi rapproché.",
        }[grade_ar]

    wrong = [r for r in rows if not r["correct"]]
    return {
        "attempt": attempt, "exam": exam, "n": n, "n_answered": n_answered, "n_correct": n_correct,
        "unanswered": n - n_answered, "score": score, "total": total, "pct": pct,
        "grade": grade, "grade_css": grade_css, "summary": summary,
        "by_level": by_level, "by_topic": by_topic, "weak": weak, "strong": strong,
        "verdict": verdict, "verdict_css": verdict_css, "indicators": indicators,
        "p_chance": round(100 * p_chance), "expected": round(expected, 1),
        "duration_min": duration_min, "recs": recs, "wrong": wrong,
        "lang": lang, "languages": report_languages(exam),
        "subject": SUBJECTS_FR.get(subject, subject) if fr else subject,
        "L": dict(LABELS[lang], no_ind=LABELS[lang]["no_ind"].format(round(expected))),
    }
