"""تحديد المحور (الدرس) الذي يقيسه السؤال تلقائيًا من نصه وخياراته، عندما لا يحدده الأستاذ.

القواعد مرتبة: أول محور تتطابق كلماته مع نص السؤال هو المعتمد.
القاعدة (المحور، نمط لنص السؤال، نمط اختياري يُطبَّق على كل خيار بمفرده).
"""
import re

RULES = {
    "الرياضيات": [
        ("الإحصاء والاحتمالات", r"factorielle|P\(A|probabilit|moyenne|médiane|effectif|diagramme|dé ordinaire|urne"
                                r"|combinaison|arrangement|façons|codes|anagramme|fréquence|pièce|échantillon|étendue|mode de"),
        ("المتتاليات", r"suite|uₙ|u₀|1 \+ 2 \+"),
        ("الدوال والتحليل", r"application|injective|f'\(|fonction|f\(x\)|dérivée|lim |primitive|tangente|asymptote"
                            r"|courbe|minimum|maximum"),
        ("حساب المثلثات والزوايا الموجهة", r"°\s*correspond|\bcos|\bsin|\btan|\brad\b|angle orienté|π/"),
        ("الأشعة والمعلم والمرجح", r"vecteur|⃗|coordonnées|repère|barycentre|produit scalaire|milieu de|distance AB"
                                  r"|droite passant|coefficient directeur|ordonnée à l'origine|équation de la droite"
                                  r"|cercle de centre O"),
        ("التحويلات الهندسية", r"symétr|translation|rotation|homothétie|image du point|image d'un|composée"),
        ("الهندسة في الفضاء", r"cube|pavé|prisme|pyramide|cône|volume|sphère|cylindre|faces|espace"),
        ("الأعداد الحقيقية والترتيب", r"\|−?\w|intervalle|ensemble des réels"),
        ("المعادلات والمتراجحات والأنظمة", r"équation|inéquation|système|solution|matrice|déterminant|racine double"
                                           r"|discriminant"),
        ("الحساب الحرفي", r"développe|factorise|réduis|polynôme|\(a − b\)²|x³ − 1"),
        ("الجذور والقوى", r"√|10⁻|10⁴|puissance|scientifique|\d[²³⁴⁵]|irrationnel"),
        ("التناسبية والنسب المئوية", r"%|proportionnalit|échelle|coût|prix|\bUM\b|vitesse|remise|robinet"),
        ("الهندسة المستوية", r"triangle|angle|cercle|disque|parallélogramme|losange|rectangle|carré|périmètre|aire"
                             r"|thalès|pythagore|médiatrice|segment|droite|figure|hexagone|trapèze|projeté|diagonale"),
        ("الكسور والأعداد العشرية", r"fraction|/|décimal|arrondi|,\d"),
        ("الأعداد الطبيعية والعمليات", r"chiffre|divisible|multiple|pgcd|premier|division|reste|diviseur|calcule|nombre"),
    ],
    "الفيزياء والكيمياء": [
        ("الكيمياء العضوية", r"gaz naturel|alcane|alcène|alcyne|benzène|alcool|méthane|éthanol|isomère|propane"
                             r"|carboxylique|acétylène|C₄H₁₀|CH₃"),
        ("الأكسدة والاختزال والأعمدة", r"oxyd|réduct|\bpile|Cu²⁺|Zn"),
        ("المحاليل والأحماض والقواعد", r"solution|\bpH\b|acide|basique|neutre|concentration|dilu|soluté|solvant"
                                       r"|\bions?\b|chlorure|H₃O"),
        ("المادة والتفاعلات الكيميائية", r"réaction|combustion|équation chimique|équilibrée|masse molaire|\bmol\b|mole"
                                          r"|atome|molécule|électron|proton|neutron|octet|Avogadro|réactif|covalente"),
        ("المواد", r"matériau|plastique|verre|métal|recycl|aimant"),
        ("البصريات", r"grandissement|lentille|réflexion|réfraction|lumi|miroir|vergence|foyer|rayon|optique"),
        ("المغناطيسية", r"magnétique|solénoïde|tesla"),
        ("الكهرباء", r"résistance|tension|intensité|courant|générateur|électrique|kWh|condensateur|charge|coulomb|ohm"
                     r"|ampère|voltmètre|nœud|dipôle|oscillo|secteur|fréquence|sinusoïdale|puissance|circuit"),
        ("الحرارة", r"chaleur|température|fusion|thermique|°C"),
        ("الميكانيك", r"force|poids|masse|vitesse|travail|énergie|ressort|archimède|équilibre|mouvement|accélération"
                      r"|chute|dynamomètre|pesanteur|volumique|flotte|moteur"),
    ],
    "العلوم الطبيعية": [
        ("الطاقة العضلية والتنفس", r"contraction|contractile|strié|ATP|respiration|fermentation|sarcomère|actine|myosine|glycolyse"
                                   r"|phosphocréatine|crampe|fatigue"),
        ("الوراثة", r"transcription|traduction|ADN|ARN|chromosome|mitose|méiose|codon|mutation|génétique|nucléot"
                    r"|réplication|trisomie|brin|gamète humain"),
        ("الجيولوجيا", r"lithosph|roche|séisme|sism|volcan|plaque|magma|lave|dorsale|subduction|himalaya|épicentre"
                       r"|basalte|granite|métamorph|richter|marbre"),
        ("الهضم والتغذية", r"aliment|digestion|enzyme|amylase|pepsine|bile|intestin|villosit|protide|glucide|lipide"
                           r"|amidon|glucose|fehling|iodée|biuret|carence|kwashiorkor|lait|nutriment"),
        ("التبادلات الخلوية", r"osmose|plasmolyse|turgescen|hypertonique|hypotonique|diffusion|endocytose|exocytose"
                              r"|perméabilit|globule rouge|transport actif|oignon"),
        ("التكاثر", r"gamète|spermatozoïde|ovule|ovaire|testicule|fécondation|grossesse|ovulation|cycle|nidation"
                    r"|placenta|hormone sexuelle|testostérone|préservatif"),
        ("الجهاز العصبي والحركة", r"mouvements? volontaire|flexion|muscle|neurone|nerveu|nerf|réflexe|cerveau|moelle"
                                  r"|synapse|drogue|alcool"),
        ("البيئة", r"matière organique|lion|écosystème|chaîne alimentaire|producteur|consommateur|décomposeur"
                   r"|désertification|photosynthèse|abiotique|prédation|reboisement|énergie"),
        ("الخلية", r"être vivant|cellule|noyau|organite|chloroplaste|paroi|microscope|membrane|mitochondrie"),
    ],
    "الفرنسية": [
        ("فهم النص", r"d'après le texte|dans le texte"),
        ("التصريف", r"présent\)|passé composé|imparfait|futur|conditionnel|subjonctif|gérondif|participe"
                    r"|adjectif verbal|\([a-zéèêâîôû]+(er|ir|re|oir)(,[^)]*)?\)\s*$"),
        ("النحو", r"pronom|relati|complément|phrase|discours|voix|passive|comparatif|superlatif|négati"
                  r"|subordonnée|remplace|devient",
         r"^(dont|où|que|qui|quoi|y|en|le|la|lui|les|l'|mais|donc|car|pour|parce que|parce qu'|bien que|bien qu'"
         r"|depuis|il y a|dans|malgré|grâce à|à cause de|sous|sur|entre|parmi|moins|plus|aussi|autant|il|on|elle|ce)$"),
        ("الإملاء", r"féminin|pluriel|« des robes|« une fille",
         r"^(a|à|ont|on|leur|leurs|tout|tous|toute|toutes|c'est|s'est|ses|ces|quand|quant|qu'en|du|de la|des|de l'"
         r"|fait|est|va|réviser|révisé|révisez)$"),
        ("المفردات", r"contraire|synonyme|s'appelle|personne qui|frère|fille de|saison|pièce où|lexique|mot|adverbe"
                     r"|formule|lettre|protège|___"),
    ],
    "العربية": [
        ("فهم النص والثقافة", r"اقرأ النص|المحظرة|أبي الأسود|ثمامة|امسيكه|أوداغست|المعجم|معنى|مرادف|ضد"),
        ("البلاغة والعروض", r"بين كلمتي|قول الشاعر|قوله تعالى|تشبيه|استعارة|طباق|جناس|مقابلة|بحر|تفعيل|عروض"
                            r"|البيت الشعري|مجاز|إنشائي|خبرية|محسّن"),
        ("الإملاء والترقيم", r"همزة|التاء|الألف اللينة|الكتابة الصحيحة|علامة|اللام|اكتب"),
        ("الصرف", r"وزن|مصدر|اسم الفاعل|اسم المفعول|صيغة مبالغة|اسم الآلة|اسم المكان|اسم الزمان|صحيح|معتل|مجرد"
                  r"|مزيد|متعد|للمجهول|مثنى|جمع|مؤنث|مفرد|المضارع من|الأمر من|فعل:|فعلٌ|الممنوع|ممنوع من الصرف"),
        ("النحو", r"مبني|نكرة|نواصب|جوازم|أفعال الشروع|أسلوب|«هل»|إعراب|فاعل|مفعول|مبتدأ|خبر|حال|تمييز|نعت|بدل"
                  r"|منادى|إنّ|إنَّ|كان|لا|استثناء|جملة|مضاف|توكيد|عطف|تحذير|إغراء|جزم|نصب|رفع|جر|أداة|اسم|حرف"
                  r"|ضمير|إشارة|موصول"),
    ],
}

DEFAULT_TOPIC = "محاور أخرى"

# نصائح عامة لكل محور (تُستعمل في توصيات التقرير)
ADVICE = {
    "الكسور والأعداد العشرية": "مراجعة جمع الكسور وضربها واختزالها، والتحويل بين الكسر والعدد العشري.",
    "الأعداد الطبيعية والعمليات": "التدرب على العمليات الأربع والقسمة الإقليدية وقواعد قابلية القسمة وأولويات الحساب.",
    "التناسبية والنسب المئوية": "حل مسائل التناسب (الرابع المتناسب، السلّم، النسبة المئوية، السرعة) خطوة بخطوة.",
    "الهندسة المستوية": "مراجعة خواص المثلث والرباعيات والدائرة، ونظريتي فيثاغورس وطاليس، مع رسم الشكل دائمًا.",
    "الهندسة في الفضاء": "حفظ قوانين الحجوم والمساحات (المكعب، متوازي المستطيلات، الهرم، المخروط) والتدرب على تطبيقها.",
    "الأعداد الحقيقية والترتيب": "مراجعة المجالات والقيمة المطلقة والمقارنة بين الأعداد الحقيقية.",
    "الجذور والقوى": "مراجعة قواعد القوى وتبسيط الجذور والكتابة العلمية.",
    "الحساب الحرفي": "التدرب على النشر والتحليل والمتطابقات الشهيرة.",
    "المعادلات والمتراجحات والأنظمة": "حل معادلات ومتراجحات وأنظمة كثيرة مع التحقق من الحل بالتعويض.",
    "الأشعة والمعلم والمرجح": "مراجعة إحداثيات شعاع ومنتصف قطعة ومعادلة مستقيم والجداء السلمي.",
    "التحويلات الهندسية": "مراجعة التناظر والانسحاب والدوران والتحاكي وتطبيقها على نقاط في معلم.",
    "حساب المثلثات والزوايا الموجهة": "حفظ القيم الخاصة لـ cos وsin وtan والعلاقات المثلثية الأساسية.",
    "الدوال والتحليل": "مراجعة حساب الصور والمشتقات والنهايات وقراءة المنحنيات.",
    "المتتاليات": "مراجعة الحد العام ومجموع الحدود للمتتاليات الحسابية والهندسية.",
    "الإحصاء والاحتمالات": "مراجعة المعدل والوسيط والتكرارات، وحساب الاحتمالات والعدّ.",
    "الميكانيك": "مراجعة قوانين الوزن والكتلة الحجمية والقوى والشغل والطاقة مع الانتباه للوحدات.",
    "الكهرباء": "مراجعة قانون أوم والقدرة والطاقة الكهربائية وتجميع المقاومات، مع التحويل الصحيح للوحدات.",
    "البصريات": "مراجعة قوانين الانعكاس والانكسار وخصائص العدسات ورسم مسار الأشعة.",
    "المغناطيسية": "مراجعة المجال المغناطيسي وخطوطه وتأثير شدة التيار.",
    "الحرارة": "مراجعة قانون كمية الحرارة Q = m·c·Δθ وتغيرات الحالة.",
    "المواد": "مراجعة أنواع المواد وخصائصها (ناقلة، عازلة، مصدرها) وأهمية التدوير.",
    "المادة والتفاعلات الكيميائية": "مراجعة المول والكتلة المولية وموازنة المعادلات وبنية الذرة.",
    "المحاليل والأحماض والقواعد": "مراجعة التركيز والتخفيف وسلّم pH والكشف عن الأيونات.",
    "الكيمياء العضوية": "مراجعة الصيغ العامة وتسمية المركبات العضوية وتفاعلاتها المميزة.",
    "الأكسدة والاختزال والأعمدة": "مراجعة المؤكسد والمختزل والأزواج وعمل الأعمدة.",
    "الخلية": "مراجعة مكونات الخلية الحيوانية والنباتية ودور كل عضية، مع التدرب على الرسوم التخطيطية.",
    "التكاثر": "مراجعة الجهاز التناسلي والدورة الشهرية والإخصاب ومراحل الحمل.",
    "الجهاز العصبي والحركة": "مراجعة العصبون والقوس الانعكاسية وانتقال الرسالة العصبية والعضلات المتضادة.",
    "الجيولوجيا": "مراجعة أنواع الصخور والزلازل والبراكين وحركة الصفائح.",
    "البيئة": "مراجعة السلاسل الغذائية ومكونات النظام البيئي ومكافحة التصحر.",
    "التبادلات الخلوية": "مراجعة الحلول وانتقال الماء والمواد عبر الغشاء (الحلولية، الانتشار).",
    "الهضم والتغذية": "مراجعة أنواع الأغذية والكشف عنها ودور الإنزيمات ومراحل الهضم والامتصاص.",
    "الوراثة": "مراجعة بنية ADN وتكامل القواعد والانقسام والاستنساخ والترجمة.",
    "الطاقة العضلية والتنفس": "مراجعة التنفس الخلوي والتخمر وATP وآلية التقلص العضلي.",
    "فهم النص": "القراءة اليومية لنصوص قصيرة والإجابة عن أسئلة الفهم مع العودة إلى النص قبل الإجابة.",
    "التصريف": "مراجعة جداول تصريف الأفعال في الأزمنة الأساسية (المضارع، الماضي المركب، الناقص، المستقبل).",
    "الإملاء": "مراجعة الكلمات المتشابهة في النطق (a/à، ont/on، leur/leurs، c'est/s'est...) وقواعد المطابقة.",
    "النحو": "مراجعة القواعد الأساسية وتطبيقها على أمثلة كثيرة.",
    "المفردات": "توسيع الرصيد اللغوي بالمطالعة وحفظ المرادفات والأضداد.",
    "فهم النص والثقافة": "القراءة المنتظمة وفهم معاني الكلمات من السياق، ومراجعة نصوص الكتاب المدرسي.",
    "البلاغة والعروض": "مراجعة أركان التشبيه وأنواع المحسنات وتفعيلات البحور مع أمثلة.",
    "الإملاء والترقيم": "مراجعة قواعد كتابة الهمزة والتاء والألف اللينة وعلامات الترقيم.",
    "الصرف": "مراجعة الميزان الصرفي والمشتقات (اسم الفاعل والمفعول...) وأنواع الأفعال.",
}


def guess_topic(subject_name, text, choices=()):
    """يعيد اسم المحور الأنسب لنص السؤال (وخياراته) في المادة المعطاة."""
    text = text or ""
    opts = [c.strip().lower() for c in choices if c and c.strip()]
    for rule in RULES.get(subject_name, []):
        topic, pattern = rule[0], rule[1]
        choice_pattern = rule[2] if len(rule) > 2 else None
        if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
            return topic
        if choice_pattern and opts and sum(bool(re.match(choice_pattern, o)) for o in opts) >= 2:
            return topic
    return DEFAULT_TOPIC


def level_from_points(points):
    """في امتحانات القبول: نقطة = بسيط، نقطتان = متوسط، 3 نقاط = صعب."""
    try:
        p = float(points)
    except (TypeError, ValueError):
        return ""
    return {1.0: "E", 2.0: "M", 3.0: "H"}.get(p, "")
