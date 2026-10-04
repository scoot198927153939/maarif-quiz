# Quiz El Maarif · منصة الامتحانات

تطبيق ويب (Django + SQLite) لإجراء امتحانات اختيار من متعدد في المدرسة، بواجهة عربية.

## التشغيل على الحاسوب

يلزم **Python 3.10 أو أحدث**.

```bash
cd quiz-el-maarif
python -m venv .venv
# ويندوز:  .venv\Scripts\activate      لينكس/ماك:  source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate          # ينشئ قاعدة البيانات مع الأقسام والمواد
python manage.py seed_demo        # (اختياري) حسابات وامتحان تجريبي
python manage.py runserver 0.0.0.0:8000
```

ثم افتح `http://127.0.0.1:8000` في المتصفح. أجهزة التلاميذ على نفس الشبكة تفتح `http://<عنوان-IP-للحاسوب>:8000`.

لإنشاء حساب المشرف الحقيقي بدلاً من الحساب التجريبي:

```bash
python manage.py createsuperuser
```

### الحسابات التجريبية (بعد `seed_demo`)

| الدور | اسم المستخدم | كلمة المرور |
|---|---|---|
| مشرف | admin | admin123 |
| أستاذ رياضيات | prof | prof123 |
| تلميذ 1AS | eleve1 | 1234 |
| تلميذ 7SN | eleve7 | 1234 |

**غيّر كلمات المرور هذه أو احذف الحسابات قبل الاستعمال الحقيقي.**

## الأدوار

- **المشرف**: كل الصلاحيات. يضيف الأساتذة والتلاميذ (يدوياً أو من Excel)، يحدد لكل أستاذ أقسامه ومواده، يرى كل الامتحانات والنتائج. صفحة «الإعدادات» (`/admin`) لتعديل الأقسام والمواد.
- **الأستاذ**: ينشئ امتحانات لأقسامه ومواده فقط، يضيف الأسئلة (النص، الخيارات A–D، رمز الإجابة الصحيحة، النقاط، صورة توضيحية) أو يستوردها من Excel، ينشر الامتحان، ويرى النقاط لكل امتحان ولكل قسم مع تصدير Excel. يمكنه السماح لتلميذ بإعادة الامتحان.
- **التلميذ**: يرى امتحانات قسمه فقط، يجريها مرة واحدة، ويرى نتيجته والتصحيح (إذا سمح الأستاذ بذلك).

## الأقسام والمواد (تُنشأ تلقائياً)

- 1AS 2AS 3AS 4AS: الرياضيات، العربية، الفرنسية
- 5MA 5SN 6MA 6SN 7MA 7SN: الرياضيات، الفيزياء والكيمياء، العلوم الطبيعية

## ملفات Excel

النماذج موجودة في مجلد `samples/` ويمكن تحميلها أيضاً من داخل التطبيق:

- `نموذج_الأسئلة.xlsx`: الأعمدة `السؤال | A | B | C | D | الإجابة الصحيحة | النقاط`. رمز الإجابة يقبل A/B/C/D أو أ/ب/ج/د أو 1/2/3/4. إذا كان في الملف خطأ لا يُستورد شيء ويظهر رقم السطر.
- `نموذج_التلاميذ.xlsx`: الأعمدة `اسم المستخدم | الاسم الكامل | كلمة المرور | القسم`.

الصور تُضاف لكل سؤال من زر «تعديل» بعد الاستيراد.

## الحماية من الغش

- الامتحان يعمل في وضع ملء الشاشة، ويُمنع النسخ واللصق والقائمة اليمنى واختصارات لوحة المفاتيح وزر الرجوع.
- مغادرة الصفحة أو تغيير النافذة أو الخروج من ملء الشاشة تُسجَّل كمحاولة خروج، وتظهر للأستاذ في صفحة النتائج. بعد 3 محاولات يُسلَّم الامتحان تلقائياً (يمكن تغيير العدد بمتغير البيئة `EXAM_MAX_VIOLATIONS`).
- ما دام للتلميذ امتحان جارٍ، أي صفحة أخرى في التطبيق تعيده إلى الامتحان.
- المؤقت محسوب في الخادم: عند انتهاء الوقت يُسلَّم الامتحان بالإجابات المحفوظة، حتى لو أُغلق المتصفح.
- إجابة كل سؤال تُحفظ فوراً، فلا تضيع إذا انقطع الاتصال أو أُعيد تحميل الصفحة.

**ملاحظة:** المتصفح العادي لا يستطيع منع التلميذ تماماً من فتح برنامج آخر أو استعمال هاتف؛ التطبيق يكشف ذلك ويعاقب عليه. لقفل كامل للجهاز، استعمل **Safe Exam Browser** (مجاني) أو وضع Kiosk في Chrome على أجهزة المدرسة مع توجيهه إلى عنوان التطبيق.

## الاختبارات

```bash
python manage.py test quiz
```

## النشر المجاني على الإنترنت (PythonAnywhere)

PythonAnywhere يستضيف تطبيقات Django مجاناً، وتبقى قاعدة البيانات (SQLite) محفوظة. سيكون العنوان `https://USERNAME.pythonanywhere.com` (استبدل USERNAME باسم حسابك في كل الخطوات).

1. أنشئ حساباً مجانياً (Beginner) على https://www.pythonanywhere.com
2. من تبويب **Consoles** افتح **Bash** ونفّذ:

   ```bash
   git clone -b django-app https://github.com/scoot198927153939/maarif-quiz.git
   cd maarif-quiz
   mkvirtualenv --python=python3.10 quiz
   pip install -r requirements.txt
   export DJANGO_DEBUG=0
   python manage.py migrate
   python manage.py collectstatic --noinput
   python manage.py createsuperuser      # حساب المشرف
   ```

3. من تبويب **Web** اضغط **Add a new web app** ثم **Manual configuration** ثم **Python 3.10**.
4. في نفس الصفحة:
   - **Source code**: `/home/USERNAME/maarif-quiz`
   - **Virtualenv**: `/home/USERNAME/.virtualenvs/quiz`
   - فعّل **Force HTTPS**.
5. اضغط رابط **WSGI configuration file**، احذف كل محتواه وضع مكانه:

   ```python
   import os, sys
   sys.path.insert(0, "/home/USERNAME/maarif-quiz")
   os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
   os.environ["DJANGO_DEBUG"] = "0"
   os.environ["DJANGO_ALLOWED_HOSTS"] = "USERNAME.pythonanywhere.com"
   os.environ["DJANGO_CSRF_TRUSTED_ORIGINS"] = "https://USERNAME.pythonanywhere.com"
   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```

6. احفظ، ثم ارجع إلى تبويب **Web** واضغط **Reload**. افتح `https://USERNAME.pythonanywhere.com`.

**نقل البيانات الموجودة من الحاسوب** (الامتحانات والأسئلة وصورها والتلاميذ والنتائج) بدل `createsuperuser`:

1. على الحاسوب: أوقف start.bat، ثم ضع `db.sqlite3` ومجلد `media` في ملف مضغوط واحد `maarif-data.zip`.
2. في PythonAnywhere من تبويب **Files** افتح `/home/USERNAME/maarif-quiz` وارفع `maarif-data.zip` (الحد 100 ميغابايت للملف).
3. في **Bash**:

   ```bash
   cd ~/maarif-quiz && workon quiz
   unzip -o maarif-data.zip && rm maarif-data.zip
   export DJANGO_DEBUG=0 && python manage.py migrate
   ```

4. **Reload** من تبويب Web. الدخول بنفس الحسابات وكلمات المرور التي على الحاسوب.

**تحديث التطبيق لاحقاً** (بعد أي تعديل على GitHub):

```bash
cd ~/maarif-quiz && workon quiz && git pull
export DJANGO_DEBUG=0 && python manage.py migrate && python manage.py collectstatic --noinput
```

ثم **Reload** من تبويب Web.

ملاحظات الحساب المجاني: يجب الضغط على زر **Run until 3 months from today** في تبويب Web مرة كل 3 أشهر وإلا يتوقف الموقع، والقوة محدودة (مناسبة لقسم أو قسمين في نفس الوقت؛ لامتحان كل المدرسة معاً يُنصح بالحساب المدفوع أو بتشغيله على حاسوب في شبكة المدرسة).
