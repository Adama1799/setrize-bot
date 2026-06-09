---
name: "github-setrise3"
description: "قراءة وكتابة ملفات setrise3 على GitHub"
version: "1.0.0"
tools: ["shell", "web"]
---

# GitHub SetRise3 Skill

## قراءة ملف
curl -s \
  -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/rkm2004europe/setrise3/contents/{PATH}"

## إنشاء ملف
curl -s -X PUT \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  "https://api.github.com/repos/rkm2004europe/setrise3/contents/{PATH}" \
  -d '{"message": "feat: add file", "content": "BASE64"}'

## تحديث ملف (مع SHA)
curl -s -X PUT \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  "https://api.github.com/repos/rkm2004europe/setrise3/contents/{PATH}" \
  -d '{"message": "update file", "content": "BASE64", "sha": "SHA_HERE"}'
