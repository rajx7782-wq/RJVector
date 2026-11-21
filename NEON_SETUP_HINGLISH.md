# RJVector + Neon Setup (Hinglish)

## Important
RJVector Python Flask + Psycopg 3 app hai. Is repo mein `package.json` / `neon.ts` nahi hai,
isliye Node-based `neon init` / `neon deploy` command is app ke liye required nahi.
Neon PostgreSQL ko `DATABASE_URL` environment variable se connect karna hai.

## 1) Neon
1. Neon Console mein apna `rjvector` project kholo.
2. `production` branch par jao, **Connect** kholo.
3. Database/role select karke pooled connection string copy karo (agar available ho).
4. Connection string private rakho. Isse chat ya GitHub par share mat karo.

## 2) Render environment variables
Render > RJVector Web Service > Environment mein ye variables add karo:
- `DATABASE_URL` = Neon connection string (Neon ka `sslmode=require` preserve karo)
- `SECRET_KEY` = long random secret
- `ADMIN_USERNAME` = `RAJ JADHAV`
- `ADMIN_INITIAL_PASSWORD` = one-time temporary password (12345 permanent password mat rakho)
- `COOKIE_SECURE` = `true`

Build command:
`pip install -r requirements.txt`

Start command:
`gunicorn app:app --workers 2 --threads 4 --timeout 120`

Deploy ke baad `/health` open karo. Expected result:
`{"status":"ok","database":"connected","app":"RJVector"}`

First Admin login ke baad password change karo. Admin account create hone ke baad
Render se `ADMIN_INITIAL_PASSWORD` remove kar do.

## 3) Local test
Python 3.12+ install karo, project folder mein:
`python -m venv .venv`
`pip install -r requirements.txt`

`.env.example` ko `.env` copy karke values fill karo. `.env` ko Git mein commit mat karna.
Then environment variables load karke `python app.py` run karo.
Open `http://127.0.0.1:5000/health`.

## 4) Android APK (deployment ke baad)
APK abhi compile nahi ki gayi hai, kyunki Android wrapper ko actual deployed HTTPS URL chahiye.
Android Studio mein `android/` folder open karo. Terminal mein:
`gradle assembleDebug -PRJVECTOR_BASE_URL=https://YOUR-LIVE-RJVECTOR-DOMAIN/`

Debug APK path:
`android/app/build/outputs/apk/debug/app-debug.apk`

Play Store / sharing ke liye signed release APK Android Studio:
Build > Generate Signed Bundle / APK > APK
Use your own signing key and keep the keystore/password private.

## Honest status
Source package Android wrapper aur Neon connection configuration deta hai. Live Neon connection,
Render deployment, end-to-end DB test, aur APK build/signing tabhi pass maana jayega jab tumhare
Neon credentials (entered privately in Render) aur live HTTPS app URL available hon.
