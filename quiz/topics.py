"""تحديد المحور (الدرس) الذي يقيسه السؤال تلقائيًا من نصه وخياراته، عندما لا يحدده الأستاذ.

القواعد مرتبة: أول محور تتطابق كلماته مع نص السؤال هو المعتمد.
القاعدة (المحور، نمط لنص السؤال، نمط اختياري يُطبَّق على كل خيار بمفرده).
"""
import re

RULES = {
    "الرياضيات": [
        ("Statistiques et probabilités", r"factorielle|P\(A|probabilit|moyenne|médiane|effectif|diagramme|dé ordinaire|urne"
                                r"|combinaison|arrangement|façons|codes|anagramme|fréquence|pièce|échantillon|étendue|mode de"),
        ("Suites numériques", r"suite|uₙ|u₀|1 \+ 2 \+"),
        ("Fonctions et analyse", r"application|injective|f'\(|fonction|f\(x\)|dérivée|lim |primitive|tangente|asymptote"
                            r"|courbe|minimum|maximum"),
        ("Trigonométrie et angles orientés", r"°\s*correspond|\bcos|\bsin|\btan|\brad\b|angle orienté|π/"),
        ("Vecteurs, repère et barycentre", r"vecteur|⃗|coordonnées|repère|barycentre|produit scalaire|milieu de|distance AB"
                                  r"|droite passant|coefficient directeur|ordonnée à l'origine|équation de la droite"
                                  r"|cercle de centre O"),
        ("Transformations du plan", r"symétr|translation|rotation|homothétie|image du point|image d'un|composée"),
        ("Géométrie dans l'espace", r"cube|pavé|prisme|pyramide|cône|volume|sphère|cylindre|faces|espace"),
        ("Nombres réels, ordre et valeur absolue", r"\|−?\w|intervalle|ensemble des réels"),
        ("Équations, inéquations et systèmes", r"équation|inéquation|système|solution|matrice|déterminant|racine double"
                                           r"|discriminant"),
        ("Calcul littéral", r"développe|factorise|réduis|polynôme|\(a − b\)²|x³ − 1"),
        ("Racines carrées et puissances", r"√|10⁻|10⁴|puissance|scientifique|\d[²³⁴⁵]|irrationnel"),
        ("Proportionnalité et pourcentages", r"%|proportionnalit|échelle|coût|prix|\bUM\b|vitesse|remise|robinet"),
        ("Géométrie plane", r"triangle|angle|cercle|disque|parallélogramme|losange|rectangle|carré|périmètre|aire"
                             r"|thalès|pythagore|médiatrice|segment|droite|figure|hexagone|trapèze|projeté|diagonale"),
        ("Fractions et nombres décimaux", r"fraction|/|décimal|arrondi|,\d"),
        ("Entiers naturels et opérations", r"chiffre|divisible|multiple|pgcd|premier|division|reste|diviseur|calcule|nombre"),
    ],
    "الفيزياء والكيمياء": [
        ("Chimie organique", r"gaz naturel|alcane|alcène|alcyne|benzène|alcool|méthane|éthanol|isomère|propane"
                             r"|carboxylique|acétylène|C₄H₁₀|CH₃"),
        ("Oxydoréduction et piles", r"oxyd|réduct|\bpile|Cu²⁺|Zn"),
        ("Solutions, acides et bases", r"solution|\bpH\b|acide|basique|neutre|concentration|dilu|soluté|solvant"
                                       r"|\bions?\b|chlorure|H₃O"),
        ("Matière et réactions chimiques", r"réaction|combustion|équation chimique|équilibrée|masse molaire|\bmol\b|mole"
                                          r"|atome|molécule|électron|proton|neutron|octet|Avogadro|réactif|covalente"),
        ("Matériaux", r"matériau|plastique|verre|métal|recycl|aimant"),
        ("Optique", r"grandissement|lentille|réflexion|réfraction|lumi|miroir|vergence|foyer|rayon|optique"),
        ("Magnétisme", r"magnétique|solénoïde|tesla"),
        ("Électricité", r"résistance|tension|intensité|courant|générateur|électrique|kWh|condensateur|charge|coulomb|ohm"
                     r"|ampère|voltmètre|nœud|dipôle|oscillo|secteur|fréquence|sinusoïdale|puissance|circuit"),
        ("Transferts thermiques", r"chaleur|température|fusion|thermique|°C"),
        ("Mécanique", r"force|poids|masse|vitesse|travail|énergie|ressort|archimède|équilibre|mouvement|accélération"
                      r"|chute|dynamomètre|pesanteur|volumique|flotte|moteur"),
    ],
    "العلوم الطبيعية": [
        ("Énergie musculaire et respiration", r"contraction|contractile|strié|ATP|respiration|fermentation|sarcomère|actine|myosine|glycolyse"
                                   r"|phosphocréatine|crampe|fatigue"),
        ("Information génétique", r"transcription|traduction|ADN|ARN|chromosome|mitose|méiose|codon|mutation|génétique|nucléot"
                    r"|réplication|trisomie|brin|gamète humain"),
        ("Géologie", r"lithosph|roche|séisme|sism|volcan|plaque|magma|lave|dorsale|subduction|himalaya|épicentre"
                       r"|basalte|granite|métamorph|richter|marbre"),
        ("Alimentation et digestion", r"aliment|digestion|enzyme|amylase|pepsine|bile|intestin|villosit|protide|glucide|lipide"
                           r"|amidon|glucose|fehling|iodée|biuret|carence|kwashiorkor|lait|nutriment"),
        ("Échanges cellulaires", r"osmose|plasmolyse|turgescen|hypertonique|hypotonique|diffusion|endocytose|exocytose"
                              r"|perméabilit|globule rouge|transport actif|oignon"),
        ("Reproduction", r"gamète|spermatozoïde|ovule|ovaire|testicule|fécondation|grossesse|ovulation|cycle|nidation"
                    r"|placenta|hormone sexuelle|testostérone|préservatif"),
        ("Système nerveux et motricité", r"mouvements? volontaire|flexion|muscle|neurone|nerveu|nerf|réflexe|cerveau|moelle"
                                  r"|synapse|drogue|alcool"),
        ("Écologie", r"matière organique|lion|écosystème|chaîne alimentaire|producteur|consommateur|décomposeur"
                   r"|désertification|photosynthèse|abiotique|prédation|reboisement|énergie"),
        ("La cellule", r"être vivant|cellule|noyau|organite|chloroplaste|paroi|microscope|membrane|mitochondrie"),
    ],
    "الفرنسية": [
        ("Compréhension du texte", r"d'après le texte|dans le texte"),
        ("Conjugaison", r"présent\)|passé composé|imparfait|futur|conditionnel|subjonctif|gérondif|participe"
                    r"|adjectif verbal|\([a-zéèêâîôû]+(er|ir|re|oir)(,[^)]*)?\)\s*$"),
        ("Grammaire", r"pronom|relati|complément|phrase|discours|voix|passive|comparatif|superlatif|négati"
                  r"|subordonnée|remplace|devient",
         r"^(dont|où|que|qui|quoi|y|en|le|la|lui|les|l'|mais|donc|car|pour|parce que|parce qu'|bien que|bien qu'"
         r"|depuis|il y a|dans|malgré|grâce à|à cause de|sous|sur|entre|parmi|moins|plus|aussi|autant|il|on|elle|ce)$"),
        ("Orthographe", r"féminin|pluriel|« des robes|« une fille",
         r"^(a|à|ont|on|leur|leurs|tout|tous|toute|toutes|c'est|s'est|ses|ces|quand|quant|qu'en|du|de la|des|de l'"
         r"|fait|est|va|réviser|révisé|révisez)$"),
        ("Vocabulaire", r"contraire|synonyme|s'appelle|personne qui|frère|fille de|saison|pièce où|lexique|mot|adverbe"
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
DEFAULT_TOPIC_FR = "Autres"

# نصائح عامة لكل محور (تُستعمل في توصيات التقرير)
ADVICE = {
    "Fractions et nombres décimaux": "مراجعة جمع الكسور وضربها واختزالها، والتحويل بين الكسر والعدد العشري.",
    "Entiers naturels et opérations": "التدرب على العمليات الأربع والقسمة الإقليدية وقواعد قابلية القسمة وأولويات الحساب.",
    "Proportionnalité et pourcentages": "حل مسائل التناسب (الرابع المتناسب، السلّم، النسبة المئوية، السرعة) خطوة بخطوة.",
    "Géométrie plane": "مراجعة خواص المثلث والرباعيات والدائرة، ونظريتي فيثاغورس وطاليس، مع رسم الشكل دائمًا.",
    "Géométrie dans l'espace": "حفظ قوانين الحجوم والمساحات (المكعب، متوازي المستطيلات، الهرم، المخروط) والتدرب على تطبيقها.",
    "Nombres réels, ordre et valeur absolue": "مراجعة المجالات والقيمة المطلقة والمقارنة بين الأعداد الحقيقية.",
    "Racines carrées et puissances": "مراجعة قواعد القوى وتبسيط الجذور والكتابة العلمية.",
    "Calcul littéral": "التدرب على النشر والتحليل والمتطابقات الشهيرة.",
    "Équations, inéquations et systèmes": "حل معادلات ومتراجحات وأنظمة كثيرة مع التحقق من الحل بالتعويض.",
    "Vecteurs, repère et barycentre": "مراجعة إحداثيات شعاع ومنتصف قطعة ومعادلة مستقيم والجداء السلمي.",
    "Transformations du plan": "مراجعة التناظر والانسحاب والدوران والتحاكي وتطبيقها على نقاط في معلم.",
    "Trigonométrie et angles orientés": "حفظ القيم الخاصة لـ cos وsin وtan والعلاقات المثلثية الأساسية.",
    "Fonctions et analyse": "مراجعة حساب الصور والمشتقات والنهايات وقراءة المنحنيات.",
    "Suites numériques": "مراجعة الحد العام ومجموع الحدود للمتتاليات الحسابية والهندسية.",
    "Statistiques et probabilités": "مراجعة المعدل والوسيط والتكرارات، وحساب الاحتمالات والعدّ.",
    "Mécanique": "مراجعة قوانين الوزن والكتلة الحجمية والقوى والشغل والطاقة مع الانتباه للوحدات.",
    "Électricité": "مراجعة قانون أوم والقدرة والطاقة الكهربائية وتجميع المقاومات، مع التحويل الصحيح للوحدات.",
    "Optique": "مراجعة قوانين الانعكاس والانكسار وخصائص العدسات ورسم مسار الأشعة.",
    "Magnétisme": "مراجعة المجال المغناطيسي وخطوطه وتأثير شدة التيار.",
    "Transferts thermiques": "مراجعة قانون كمية الحرارة Q = m·c·Δθ وتغيرات الحالة.",
    "Matériaux": "مراجعة أنواع المواد وخصائصها (ناقلة، عازلة، مصدرها) وأهمية التدوير.",
    "Matière et réactions chimiques": "مراجعة المول والكتلة المولية وموازنة المعادلات وبنية الذرة.",
    "Solutions, acides et bases": "مراجعة التركيز والتخفيف وسلّم pH والكشف عن الأيونات.",
    "Chimie organique": "مراجعة الصيغ العامة وتسمية المركبات العضوية وتفاعلاتها المميزة.",
    "Oxydoréduction et piles": "مراجعة المؤكسد والمختزل والأزواج وعمل الأعمدة.",
    "La cellule": "مراجعة مكونات الخلية الحيوانية والنباتية ودور كل عضية، مع التدرب على الرسوم التخطيطية.",
    "Reproduction": "مراجعة الجهاز التناسلي والدورة الشهرية والإخصاب ومراحل الحمل.",
    "Système nerveux et motricité": "مراجعة العصبون والقوس الانعكاسية وانتقال الرسالة العصبية والعضلات المتضادة.",
    "Géologie": "مراجعة أنواع الصخور والزلازل والبراكين وحركة الصفائح.",
    "Écologie": "مراجعة السلاسل الغذائية ومكونات النظام البيئي ومكافحة التصحر.",
    "Échanges cellulaires": "مراجعة الحلول وانتقال الماء والمواد عبر الغشاء (الحلولية، الانتشار).",
    "Alimentation et digestion": "مراجعة أنواع الأغذية والكشف عنها ودور الإنزيمات ومراحل الهضم والامتصاص.",
    "Information génétique": "مراجعة بنية ADN وتكامل القواعد والانقسام والاستنساخ والترجمة.",
    "Énergie musculaire et respiration": "مراجعة التنفس الخلوي والتخمر وATP وآلية التقلص العضلي.",
    "Compréhension du texte": "القراءة اليومية لنصوص قصيرة والإجابة عن أسئلة الفهم مع العودة إلى النص قبل الإجابة.",
    "Conjugaison": "مراجعة جداول تصريف الأفعال في الأزمنة الأساسية (المضارع، الماضي المركب، الناقص، المستقبل).",
    "Orthographe": "مراجعة الكلمات المتشابهة في النطق (a/à، ont/on، leur/leurs، c'est/s'est...) وقواعد المطابقة.",
    "Grammaire": "مراجعة قواعد النحو الفرنسي (الضمائر، الأسماء الموصولة، المكمّلات، المبني للمجهول...) وتطبيقها على أمثلة كثيرة.",
    "النحو": "مراجعة القواعد الأساسية وتطبيقها على أمثلة كثيرة.",
    "Vocabulaire": "توسيع الرصيد اللغوي بالمطالعة وحفظ المرادفات والأضداد.",
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
    return DEFAULT_TOPIC if subject_name == "العربية" else DEFAULT_TOPIC_FR


def level_from_points(points):
    """في امتحانات القبول: نقطة = بسيط، نقطتان = متوسط، 3 نقاط = صعب."""
    try:
        p = float(points)
    except (TypeError, ValueError):
        return ""
    return {1.0: "E", 2.0: "M", 3.0: "H"}.get(p, "")


# نفس النصائح بالفرنسية (للتقرير الفرنسي، كل المواد ماعدا العربية)
ADVICE_FR = {
    "Fractions et nombres décimaux": "Revoir l'addition, la multiplication et la simplification des fractions, et le passage fraction ↔ nombre décimal.",
    "Entiers naturels et opérations": "S'entraîner aux quatre opérations, à la division euclidienne, aux critères de divisibilité et aux priorités de calcul.",
    "Proportionnalité et pourcentages": "Résoudre pas à pas des problèmes de proportionnalité (quatrième proportionnelle, échelle, pourcentage, vitesse).",
    "Géométrie plane": "Revoir les propriétés du triangle, des quadrilatères et du cercle, les théorèmes de Pythagore et de Thalès, en faisant toujours une figure.",
    "Géométrie dans l'espace": "Apprendre les formules de volumes et d'aires (cube, pavé droit, pyramide, cône) et s'entraîner à les appliquer.",
    "Nombres réels, ordre et valeur absolue": "Revoir les intervalles, la valeur absolue et la comparaison des nombres réels.",
    "Racines carrées et puissances": "Revoir les règles des puissances, la simplification des racines et l'écriture scientifique.",
    "Calcul littéral": "S'entraîner au développement, à la factorisation et aux identités remarquables.",
    "Équations, inéquations et systèmes": "Résoudre de nombreuses équations, inéquations et systèmes en vérifiant la solution par substitution.",
    "Vecteurs, repère et barycentre": "Revoir les coordonnées d'un vecteur et du milieu, l'équation d'une droite et le produit scalaire.",
    "Transformations du plan": "Revoir la symétrie, la translation, la rotation et l'homothétie, et les appliquer à des points d'un repère.",
    "Trigonométrie et angles orientés": "Apprendre les valeurs remarquables de cos, sin et tan et les relations trigonométriques de base.",
    "Fonctions et analyse": "Revoir le calcul d'images, de dérivées et de limites, et la lecture de courbes.",
    "Suites numériques": "Revoir le terme général et la somme des termes des suites arithmétiques et géométriques.",
    "Statistiques et probabilités": "Revoir la moyenne, la médiane et les effectifs, le calcul de probabilités et le dénombrement.",
    "Mécanique": "Revoir les lois du poids, la masse volumique, les forces, le travail et l'énergie, en faisant attention aux unités.",
    "Électricité": "Revoir la loi d'Ohm, la puissance et l'énergie électriques et l'association de résistances, avec les bonnes conversions d'unités.",
    "Optique": "Revoir les lois de la réflexion et de la réfraction, les propriétés des lentilles et le tracé des rayons.",
    "Magnétisme": "Revoir le champ magnétique, ses lignes de champ et l'effet de l'intensité du courant.",
    "Transferts thermiques": "Revoir la relation Q = m·c·Δθ et les changements d'état.",
    "Matériaux": "Revoir les familles de matériaux et leurs propriétés (conducteur, isolant, origine) et l'intérêt du recyclage.",
    "Matière et réactions chimiques": "Revoir la mole, la masse molaire, l'équilibrage des équations et la structure de l'atome.",
    "Solutions, acides et bases": "Revoir la concentration, la dilution, l'échelle de pH et les tests d'identification des ions.",
    "Chimie organique": "Revoir les formules générales, la nomenclature des composés organiques et leurs réactions caractéristiques.",
    "Oxydoréduction et piles": "Revoir oxydant et réducteur, les couples et le fonctionnement des piles.",
    "La cellule": "Revoir les constituants des cellules animale et végétale et le rôle de chaque organite, avec des schémas.",
    "Reproduction": "Revoir l'appareil reproducteur, le cycle menstruel, la fécondation et les étapes de la grossesse.",
    "Système nerveux et motricité": "Revoir le neurone, l'arc réflexe, la transmission du message nerveux et les muscles antagonistes.",
    "Géologie": "Revoir les types de roches, les séismes, les volcans et la tectonique des plaques.",
    "Écologie": "Revoir les chaînes alimentaires, les composantes d'un écosystème et la lutte contre la désertification.",
    "Échanges cellulaires": "Revoir l'osmose, la diffusion et le passage de l'eau et des substances à travers la membrane.",
    "Alimentation et digestion": "Revoir les types d'aliments et leur mise en évidence, le rôle des enzymes, la digestion et l'absorption.",
    "Information génétique": "Revoir la structure de l'ADN, la complémentarité des bases, la division cellulaire, la transcription et la traduction.",
    "Énergie musculaire et respiration": "Revoir la respiration cellulaire, la fermentation, l'ATP et le mécanisme de la contraction musculaire.",
    "Compréhension du texte": "Lire chaque jour de courts textes et répondre à des questions de compréhension en revenant au texte avant de répondre.",
    "Conjugaison": "Revoir les tableaux de conjugaison aux temps essentiels (présent, passé composé, imparfait, futur).",
    "Orthographe": "Revoir les homophones (a/à, ont/on, leur/leurs, c'est/s'est...) et les règles d'accord.",
    "Grammaire": "Revoir les règles de grammaire (pronoms, relatifs, compléments, voix passive...) et les appliquer sur de nombreux exemples.",
    "Vocabulaire": "Enrichir son vocabulaire par la lecture et apprendre synonymes et contraires.",
}
