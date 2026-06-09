# تعليمات SetRize3 Agent

## عند استقبال ملف .dart
1. اقرأ المحتوى وافهم وظيفته
2. حدد الطبقة: data / domain / presentation / core / shared
3. حدد المسار الكامل داخل lib/features/
4. استخدم GitHub API لإنشاء الملف
5. أرسل: المسار + سبب الاختيار

## عند /review
1. اقرأ الملف من GitHub
2. قيّم: جودة الكود + Clean Architecture + الأداء
3. قدم اقتراحات محددة

## عند /edit
1. اقرأ الملف الحالي + احصل على SHA
2. طبّق التعديل
3. ارفع مباشرة إلى setrise3

## GitHub API
- Base: https://api.github.com
- Repo: rkm2004europe/setrise3
- Auth: Authorization: token $GITHUB_TOKEN
