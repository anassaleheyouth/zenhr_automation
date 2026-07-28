# ZenHR Remote-Work Request Automation

سكريبت بيبعت طلب "Working Remotely" على ZenHR أوتوماتيك مرتين في الأسبوع، وبيبعتلك تأكيد على WhatsApp.

## 1) التثبيت (مرة واحدة بس)

افتح Command Prompt (أو PowerShell) في فولدر `zenhr_automation` واكتب:

```
pip install -r requirements.txt
playwright install chromium
```

## 2) إعداد بياناتك

1. اعمل نسخة من `config.json.example` وسميها `config.json`
2. افتح `config.json` وعبي:
   - `zenhr_email` و `zenhr_password` بتاعينك
   - `callmebot_phone`: رقمك بصيغة دولية بدون + أو 00 (مثال: `201234567890`)
   - `callmebot_apikey`: اللي جالك من CallMeBot بعد ما بعتت الرسالة على WhatsApp لرقم `+34 644 96 39 47`

**ملحوظة أمان:** ملف `config.json` فيه باسوردك - خليه على جهازك بس ومتشاركه مع حد، ومينفعش يترفع على GitHub أو أي مكان عام.

## 3) تجربة الاسكريبت يدوي الأول

قبل ما تظبطه على جدول، جربه بنفسك عشان تتأكد إنه شغال صح:

```
python zenhr_automation.py sunday
```

ده هيبعت طلب "Working Remotely" ليوم الاتنين الجاي، وهيبعتلك رسالة WhatsApp بالنتيجة.
لو حصلت مشكلة، شوف ملف `zenhr_automation.log` وملفات الـ screenshot (`error_*.png` أو `last_run_*.png`) في نفس الفولدر.

## 4) جدولة الاسكريبت على Windows Task Scheduler

افتح **Command Prompt as Administrator** واكتب الأوامر دي (غيّر `PATH_TO_PYTHON` و `PATH_TO_SCRIPT` بالمسارات الحقيقية عندك):

**Task 1 - كل يوم حد الساعة 3 العصر:**
```
schtasks /create /tn "ZenHR_RemoteWork_Sunday" /tr "PATH_TO_PYTHON\python.exe PATH_TO_SCRIPT\zenhr_automation.py sunday" /sc weekly /d SUN /st 15:00
```

**Task 2 - كل يوم تلات الساعة 3 العصر:**
```
schtasks /create /tn "ZenHR_RemoteWork_Tuesday" /tr "PATH_TO_PYTHON\python.exe PATH_TO_SCRIPT\zenhr_automation.py tuesday" /sc weekly /d TUE /st 15:00
```

مثال حقيقي (لو بايثون متثبت في المسار المعتاد والاسكريبت في `C:\Users\Anas\zenhr_automation`):
```
schtasks /create /tn "ZenHR_RemoteWork_Sunday" /tr "C:\Users\Anas\AppData\Local\Programs\Python\Python312\python.exe C:\Users\Anas\zenhr_automation\zenhr_automation.py sunday" /sc weekly /d SUN /st 15:00

schtasks /create /tn "ZenHR_RemoteWork_Tuesday" /tr "C:\Users\Anas\AppData\Local\Programs\Python\Python312\python.exe C:\Users\Anas\zenhr_automation\zenhr_automation.py tuesday" /sc weekly /d TUE /st 15:00
```

**لمعرفة مسار بايثون بالظبط:**
```
where python
```

### للتأكد إن الـ Tasks اتسجلت صح:
```
schtasks /query /tn "ZenHR_RemoteWork_Sunday"
schtasks /query /tn "ZenHR_RemoteWork_Tuesday"
```

### لو عايز تمسح Task:
```
schtasks /delete /tn "ZenHR_RemoteWork_Sunday" /f
```

## 5) التشغيل من غير ما جهازك يكون مفتوح (GitHub Actions - الأفضل)

بدل ما تعتمد على Task Scheduler على جهازك (لازم يكون مفتوح وع النت في الميعاد بالظبط)، ينفع تشغّل الاسكريبت على GitHub مجانًا، وهيشتغل حتى لو جهازك مقفول أو مسافر بيه.

### أ) اعمل Repo خاص (Private) على GitHub
1. روح على github.com واعمل repo جديد، سميه مثلاً `zenhr-automation`
2. **مهم جدًا:** خليه **Private** مش Public (فيه معلومات حساسة عن شغلك)

### ب) ارفع الملفات
من جوه فولدر `zenhr_automation` على جهازك:
```
git init
git add .
git commit -m "ZenHR automation"
git branch -M main
git remote add origin https://github.com/USERNAME/zenhr-automation.git
git push -u origin main
```
(بديل: تقدر كمان ترفع الملفات يدوي من واجهة GitHub لو مش متعود على git commands - زرار "Add file" > "Upload files")

**ملحوظة:** ملف `config.json` مش هيترفع خالص (موجود في `.gitignore`) - وده مقصود، لإننا هنحط البيانات دي في مكان تاني أأمن (Secrets).

### ج) ضيف بياناتك كـ GitHub Secrets
1. في الـ repo، روح على **Settings** → **Secrets and variables** → **Actions**
2. دوس **New repository secret** وضيف الأربعة دول واحد واحد:
   - `ZENHR_EMAIL` → إيميلك
   - `ZENHR_PASSWORD` → باسوردك
   - `CALLMEBOT_PHONE` → رقمك
   - `CALLMEBOT_APIKEY` → الـ API key بتاع CallMeBot

### د) جرب يدوي الأول
1. روح تاب **Actions** في الـ repo
2. هتلاقي الـ workflows الاتنين: "ZenHR - Sunday Remote Work Request" و "ZenHR - Tuesday Remote Work Request"
3. افتح أي واحد فيهم، دوس **Run workflow** (زرار يدوي للتجربة)
4. استنى دقيقة/دقيقتين وشوف هل خلص بعلامة ✅ خضرا ولا ❌ حمرا
5. لو فشل، دوس على الـ run نفسه وشوف تفاصيل الخطأ في اللوج

### هـ) بعد ما تتأكد إنه شغال
سيبه كده، هيشتغل لوحده أوتوماتيك كل حد وتلات الساعة 3 بتوقيت القاهرة، من غير ما تحتاج تفتح جهازك خالص.

**ملحوظة عن التوقيت:** جدول GitHub Actions (cron) بيتظبط بتوقيت UTC، وأنا حطيته على أساس القاهرة UTC+3 (توقيت صيفي). لو لقيت التوقيت طلع مختلف بساعة، افتح ملفات `.github/workflows/sunday.yml` و `tuesday.yml` وغيّر الرقم `12` في سطر الـ cron لـ `13`.

كمان GitHub مش بيضمن الميعاد بالظبط للثانية - ممكن يتأخر شوية (دقايق معدودة) في أوقات الزحمة، ده طبيعي وميأثرش على النتيجة.

## 6) ملاحظات مهمة

- الاسكريبت لازم يكون فيه اتصال إنترنت وقت الميعاد (3 العصر)، وجهازك يكون مفتوح (Task Scheduler مش هيشغله لو الجهاز مقفول تمامًا/مطفي).
- لو ZenHR غيّروا حاجة في تصميم صفحة الطلب (تغيير في أسماء الأزرار أو الـ layout)، الاسكريبت ممكن يتوقف - في الحالة دي كلمني وأنا أعدله.
- كل مرة يشتغل، بيسجل screenshot في نفس الفولدر (`last_run_*.png` أو `error_*.png`) عشان تقدر تتأكد بعينك لو حصلت مشكلة.
- رسايل WhatsApp هتيجيلك من رقم CallMeBot الرسمي (+34 644 96 39 47).
