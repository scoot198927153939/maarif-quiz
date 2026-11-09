from django.contrib.auth.hashers import PBKDF2PasswordHasher


class FastPBKDF2PasswordHasher(PBKDF2PasswordHasher):
    """نفس خوارزمية Django الافتراضية بعدد تكرارات أقل.
    خادم PythonAnywhere المجاني بطيء: مليون تكرار تأخذ قرابة ثانية لكل كلمة مرور،
    فيصير استيراد مئات التلاميذ أطول من مهلة الخادم ويبطؤ كل تسجيل دخول.
    كلمات المرور القديمة تبقى صالحة كما هي: لا يُعاد حفظها عند الدخول،
    لأن تغيير الحفظ يُخرج المستخدم من أجهزته الأخرى."""

    iterations = 100_000

    def must_update(self, encoded):
        return False
