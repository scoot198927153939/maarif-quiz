"""تحليل محاولة تلميذ: المستوى، النجاح حسب الصعوبة والمحور، مؤشرات الإجابة العشوائية، والتوصيات."""
from collections import Counter, OrderedDict
from statistics import median

from .topics import ADVICE, DEFAULT_TOPIC, guess_topic

LEVELS = OrderedDict([("E", "بسيطة"), ("M", "متوسطة"), ("H", "صعبة")])

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


def analyze(attempt):
    exam = attempt.exam
    subject = exam.subject.name
    questions = {q.id: q for q in exam.questions.prefetch_related("choices")}
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

    # حسب الصعوبة
    by_level = []
    for code, name in LEVELS.items():
        rs = [r for r in rows if r["level"] == code]
        if rs:
            c = sum(r["correct"] for r in rs)
            by_level.append({"code": code, "name": name, "n": len(rs), "correct": c, "pct": _pct(c, len(rs))})
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
    weak = [t for t in by_topic if t["pct"] < 50 and (t["n"] >= 2 or t["pct"] == 0) and t["topic"] != DEFAULT_TOPIC]
    strong = [t for t in reversed(by_topic) if t["pct"] >= 80 and t["n"] >= 2]

    # ---- مؤشرات الإجابة العشوائية ----
    indicators = []
    expected = sum(r["p_random"] for r in rows)
    p_chance = _prob_at_least(n_correct, [r["p_random"] for r in rows]) if n else 1
    chance_like = p_chance >= 0.05
    if chance_like:
        indicators.append(
            f"عدد إجاباته الصحيحة ({n_correct} من {n}) قريب مما يحصل عليه من يجيب عشوائيًا "
            f"(حوالي {expected:.0f} إجابة صحيحة بالصدفة).")
    if "E" in lvl and "H" in lvl and lvl["E"] is not None and lvl["H"] is not None and "M" in lvl:
        if lvl["E"] <= lvl["M"] + 5 and lvl["E"] < 60:
            indicators.append("لم ينجح في الأسئلة البسيطة أكثر من المتوسطة، والمعتاد أن يكون البسيط أسهل عليه؛ "
                              "هذا يدل على أن اختياره لم يكن مبنيًا على الفهم.")
    letters = Counter(r["selected"] for r in rows if r["answered"])
    if n_answered >= 10:
        letter, cnt = letters.most_common(1)[0]
        if cnt / n_answered >= 0.5:
            indicators.append(f"اختار الحرف {letter} في {cnt} سؤالًا من {n_answered} ({_pct(cnt, n_answered)}%)، "
                              "بينما الإجابات الصحيحة موزعة بالتساوي تقريبًا على A وB وC وD.")
    run, best = 1, 1
    for prev, cur in zip(rows, rows[1:]):
        run = run + 1 if cur["answered"] and cur["selected"] == prev["selected"] else 1
        best = max(best, run)
    if best >= 6:
        indicators.append(f"أجاب بنفس الحرف في {best} أسئلة متتالية.")

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
            indicators.append(f"أجاب بسرعة كبيرة: حوالي {med:.0f} ثوانٍ بين السؤال والآخر في المتوسط، "
                              "وهي مدة لا تكفي لقراءة السؤال وحله.")
    elif duration_min is not None and n and duration_min * 60 / n < 10 and n_answered >= n / 2:
        fast = True
        indicators.append(f"أنهى الامتحان في {duration_min} دقيقة فقط لـ {n} سؤال، أي أقل من 10 ثوانٍ للسؤال.")

    if chance_like and (len(indicators) >= 2 or p_chance >= 0.3):
        verdict, verdict_css = "إجاباته عشوائية على الأرجح", "ko"
    elif chance_like or len(indicators) >= 2 or fast:
        verdict, verdict_css = "في إجاباته جزء من التخمين", "warn"
    else:
        verdict, verdict_css = "إجاباته مدروسة وليست عشوائية", "ok"

    # ---- التوصيات ----
    recs = []
    if verdict_css == "ko":
        recs.append("الأولوية الأولى: ترك الإجابة العشوائية. عليه أن يقرأ كل سؤال بتمعّن، ويستبعد الخيارات الخاطئة "
                    "واحدًا واحدًا، ولا يختار إلا بعد التفكير. الإجابة العشوائية لا تعكس مستواه الحقيقي.")
    elif verdict_css == "warn":
        recs.append("التقليل من التخمين: أن يأخذ وقته في قراءة السؤال، ويحل على المسودة، ويستبعد الخيارات غير الممكنة قبل الاختيار.")
    if fast:
        recs.append("استغلال وقت الامتحان كاملًا (ساعة و45 دقيقة) ومراجعة الإجابات قبل التسليم بدل الإسراع.")
    if lvl.get("E") is not None and lvl["E"] < 60:
        recs.append("عنده نقص في الأساسيات: يجب أن يبدأ بمراجعة الدروس الأساسية وحل التمارين البسيطة في الكتاب المدرسي "
                    "حتى يتقنها، قبل الانتقال إلى التمارين الأصعب.")
    elif lvl.get("M") is not None and lvl["M"] < 50:
        recs.append("يتقن الأساسيات، لكنه يحتاج إلى التدرب على تمارين تطبيقية متعددة الخطوات (المستوى المتوسط).")
    elif lvl.get("H") is not None and lvl["H"] < 34 and pct >= 65:
        recs.append("مستواه جيد في البسيط والمتوسط؛ ليتقدم أكثر يحتاج إلى تمارين التعمق والمسائل المركبة.")
    for t in weak[:5]:
        tip = ADVICE.get(t["topic"], "مراجعة هذا الدرس في الكتاب المدرسي وحل تمارينه.")
        recs.append(f"محور «{t['topic']}» (نجح في {t['correct']} من {t['n']}): {tip}")
    unanswered = n - n_answered
    if n and unanswered / n > 0.1:
        recs.append(f"ترك {unanswered} سؤالًا بدون إجابة: عليه تنظيم الوقت، والبدء بالأسئلة التي يعرفها ثم الرجوع إلى الباقي.")
    if attempt.violations:
        recs.append(f"سُجّلت له {attempt.violations} محاولة خروج من صفحة الامتحان؛ يجب تنبيهه إلى الالتزام بقواعد الامتحان.")
    if not recs:
        recs.append("نتيجته جيدة ومتوازنة؛ يُنصح بالمحافظة على المراجعة المنتظمة وحل تمارين إضافية للتعمق.")

    summary = {
        "جيد جدًا": "مستوى ممتاز، يتقن أغلب محاور المادة.",
        "جيد": "مستوى جيد، مع بعض النقاط التي تحتاج إلى مراجعة.",
        "لا بأس به": "مستوى مقبول، لكن عنده نقائص واضحة في بعض المحاور.",
        "ضعيف": "مستوى ضعيف، يحتاج إلى مراجعة جادة ومتابعة.",
        "بلا مستوى": "لم يُظهر تحكمًا في المادة؛ يحتاج إلى إعادة بناء الأساسيات مع متابعة قريبة.",
    }[grade]

    wrong = [r for r in rows if not r["correct"]]
    return {
        "attempt": attempt, "exam": exam, "n": n, "n_answered": n_answered, "n_correct": n_correct,
        "unanswered": n - n_answered, "score": score, "total": total, "pct": pct,
        "grade": grade, "grade_css": grade_css, "summary": summary,
        "by_level": by_level, "by_topic": by_topic, "weak": weak, "strong": strong,
        "verdict": verdict, "verdict_css": verdict_css, "indicators": indicators,
        "p_chance": round(100 * p_chance), "expected": round(expected, 1),
        "duration_min": duration_min, "recs": recs, "wrong": wrong,
    }
