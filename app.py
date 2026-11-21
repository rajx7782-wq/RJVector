import os, csv, io, secrets
from datetime import datetime, date
from functools import wraps
from flask import Flask, request, jsonify, session, render_template, redirect, url_for, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','true').lower()=='true', MAX_CONTENT_LENGTH=20*1024*1024)
DATABASE_URL = os.environ.get('DATABASE_URL','')
if DATABASE_URL.startswith('postgres://'): DATABASE_URL = DATABASE_URL.replace('postgres://','postgresql://',1)
if not DATABASE_URL: raise RuntimeError('DATABASE_URL environment variable is required. Configure PostgreSQL before starting RJVector.')
pool = ConnectionPool(conninfo=DATABASE_URL, kwargs={'row_factory':dict_row}, min_size=1, max_size=5, open=True)

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users(id BIGSERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, full_name TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','student')), active BOOLEAN NOT NULL DEFAULT TRUE, must_change_password BOOLEAN NOT NULL DEFAULT FALSE, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS attendance(id BIGSERIAL PRIMARY KEY, student_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE, attendance_date DATE NOT NULL, status TEXT NOT NULL CHECK(status IN ('present','absent')), note TEXT DEFAULT '', created_at TIMESTAMPTZ DEFAULT now(), UNIQUE(student_id,attendance_date));
CREATE TABLE IF NOT EXISTS materials(id BIGSERIAL PRIMARY KEY, title TEXT NOT NULL, subject TEXT NOT NULL DEFAULT '', description TEXT DEFAULT '', file_url TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS classes(id BIGSERIAL PRIMARY KEY, title TEXT NOT NULL, subject TEXT DEFAULT '', class_url TEXT NOT NULL, starts_at TIMESTAMPTZ, description TEXT DEFAULT '', created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS announcements(id BIGSERIAL PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL, important BOOLEAN DEFAULT FALSE, created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS tests(id BIGSERIAL PRIMARY KEY, title TEXT NOT NULL, subject TEXT DEFAULT '', duration_minutes INT NOT NULL DEFAULT 30, published BOOLEAN DEFAULT FALSE, created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS questions(id BIGSERIAL PRIMARY KEY, test_id BIGINT NOT NULL REFERENCES tests(id) ON DELETE CASCADE, question TEXT NOT NULL, options JSONB NOT NULL, correct_index INT NOT NULL, marks NUMERIC(8,2) NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS submissions(id BIGSERIAL PRIMARY KEY, test_id BIGINT NOT NULL REFERENCES tests(id) ON DELETE CASCADE, student_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE, answers JSONB NOT NULL, score NUMERIC(8,2) NOT NULL DEFAULT 0, submitted_at TIMESTAMPTZ DEFAULT now(), UNIQUE(test_id,student_id));
CREATE TABLE IF NOT EXISTS fees(id BIGSERIAL PRIMARY KEY, student_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE, amount NUMERIC(10,2) NOT NULL, due_date DATE, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','paid')), note TEXT DEFAULT '', created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS homework(id BIGSERIAL PRIMARY KEY, title TEXT NOT NULL, description TEXT DEFAULT '', due_date DATE, created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS activity_logs(id BIGSERIAL PRIMARY KEY, user_id BIGINT REFERENCES users(id) ON DELETE SET NULL, action TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT now());
CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(attendance_date); CREATE INDEX IF NOT EXISTS idx_attendance_student ON attendance(student_id); CREATE INDEX IF NOT EXISTS idx_submissions_student ON submissions(student_id);
'''
def db(): return pool.connection()
def init_db():
    with db() as conn:
        for statement in SCHEMA.split(';'):
            if statement.strip(): conn.execute(statement)
        username=os.getenv('ADMIN_USERNAME','RAJ JADHAV')
        initial=os.getenv('ADMIN_INITIAL_PASSWORD','')
        if initial:
            row=conn.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()
            if not row:
                conn.execute('INSERT INTO users(username,full_name,password_hash,role,must_change_password) VALUES(%s,%s,%s,%s,%s)',(username,username,generate_password_hash(initial),'admin',True))

def current_user():
    uid=session.get('uid')
    if not uid: return None
    with db() as conn: return conn.execute('SELECT id,username,full_name,role,must_change_password FROM users WHERE id=%s AND active=true',(uid,)).fetchone()
def login_required(fn):
    @wraps(fn)
    def w(*a,**kw):
        u=current_user()
        if not u: return jsonify(error='Please log in again.'),401
        if u['must_change_password'] and request.endpoint not in ('change_password','api_logout','me'):
            return jsonify(error='Change your temporary password before using RJVector.'),403
        return fn(*a,**kw)
    return w
def admin_required(fn):
    @wraps(fn)
    def w(*a,**kw):
        u=current_user()
        if not u: return jsonify(error='Please log in again.'),401
        if u['must_change_password'] and request.endpoint not in ('change_password','api_logout','me'):
            return jsonify(error='Change your temporary password before using RJVector.'),403
        if u['role']!='admin': return jsonify(error='Admin permission required.'),403
        return fn(*a,**kw)
    return w
def log_action(uid,action):
    with db() as conn: conn.execute('INSERT INTO activity_logs(user_id,action) VALUES(%s,%s)',(uid,action))

@app.get('/')
def home(): return render_template('index.html')
@app.get('/health')
def health():
    with db() as conn: conn.execute('SELECT 1')
    return {'status':'ok','database':'connected','app':'RJVector'}
@app.get('/manifest.webmanifest')
def manifest(): return send_file('static/manifest.webmanifest',mimetype='application/manifest+json')
@app.get('/service-worker.js')
def sw(): return send_file('static/service-worker.js',mimetype='application/javascript')
@app.post('/api/login')
def api_login():
    d=request.get_json(silent=True) or {}; username=(d.get('username') or '').strip(); password=d.get('password') or ''; role=d.get('role')
    if not username or not password or role not in ('admin','student'): return jsonify(error='Username, password and account type are required.'),400
    with db() as conn: user=conn.execute('SELECT * FROM users WHERE lower(username)=lower(%s) AND role=%s AND active=true',(username,role)).fetchone()
    if not user or not check_password_hash(user['password_hash'],password): return jsonify(error='Incorrect username or password, or account type does not match.'),401
    session.clear(); session['uid']=user['id']; session.permanent=True
    log_action(user['id'],'Logged in')
    return jsonify(user={'id':user['id'],'name':user['full_name'],'username':user['username'],'role':user['role'],'must_change_password':user['must_change_password']})
@app.post('/api/logout')
@login_required
def api_logout():
    u=current_user(); log_action(u['id'],'Logged out'); session.clear(); return {'ok':True}
@app.get('/api/me')
@login_required
def me():
    u=current_user(); return {'user':u}
@app.post('/api/change-password')
@login_required
def change_password():
    d=request.get_json() or {}; old=d.get('old_password',''); new=d.get('new_password','')
    if len(new)<8: return jsonify(error='New password must contain at least 8 characters.'),400
    with db() as conn:
        row=conn.execute('SELECT password_hash FROM users WHERE id=%s',(session['uid'],)).fetchone()
        if not check_password_hash(row['password_hash'],old): return jsonify(error='Current password is incorrect.'),400
        conn.execute('UPDATE users SET password_hash=%s,must_change_password=false WHERE id=%s',(generate_password_hash(new),session['uid']))
    return {'ok':True}
@app.get('/api/dashboard')
@login_required
def dashboard():
    u=current_user()
    with db() as c:
        if u['role']=='admin':
            data={'students':c.execute("SELECT count(*) n FROM users WHERE role='student' AND active=true").fetchone()['n'],'present_today':c.execute("SELECT count(*) n FROM attendance WHERE attendance_date=current_date AND status='present'").fetchone()['n'],'tests':c.execute('SELECT count(*) n FROM tests').fetchone()['n'],'pending_fees':c.execute("SELECT coalesce(sum(amount),0) n FROM fees WHERE status='pending'").fetchone()['n']}
        else:
            data={'attendance':c.execute('SELECT count(*) n FROM attendance WHERE student_id=%s AND status=\'present\'',(u['id'],)).fetchone()['n'],'tests':c.execute('SELECT count(*) n FROM submissions WHERE student_id=%s',(u['id'],)).fetchone()['n'],'pending_fees':c.execute("SELECT coalesce(sum(amount),0) n FROM fees WHERE student_id=%s AND status='pending'",(u['id'],)).fetchone()['n']}
    return {'stats':data}
@app.get('/api/students')
@admin_required
def students():
    with db() as c: rows=c.execute("SELECT id,username,full_name,active,created_at FROM users WHERE role='student' ORDER BY full_name").fetchall()
    return {'students':rows}
@app.post('/api/students')
@admin_required
def add_student():
    d=request.get_json() or {}; name=(d.get('name') or '').strip(); username=(d.get('username') or '').strip(); password=d.get('password') or 'Student@123'
    if not name or not username: return jsonify(error='Name and username are required.'),400
    if len(password)<8: return jsonify(error='Student password must be at least 8 characters.'),400
    try:
        with db() as c: row=c.execute("INSERT INTO users(username,full_name,password_hash,role,must_change_password) VALUES(%s,%s,%s,'student',true) RETURNING id,username,full_name",(username,name,generate_password_hash(password))).fetchone()
    except psycopg.errors.UniqueViolation: return jsonify(error='This username is already in use.'),409
    log_action(session['uid'],'Added student '+username); return {'student':row},201
@app.patch('/api/students/<int:sid>')
@admin_required
def edit_student(sid):
    d=request.get_json() or {}
    with db() as c:
        row=c.execute("UPDATE users SET full_name=coalesce(%s,full_name),active=coalesce(%s,active) WHERE id=%s AND role='student' RETURNING id,username,full_name,active",(d.get('name'),d.get('active'),sid)).fetchone()
    if not row:return jsonify(error='Student not found.'),404
    return {'student':row}
@app.post('/api/students/<int:sid>/reset-password')
@admin_required
def reset_student(sid):
    pw=(request.get_json() or {}).get('password','')
    if len(pw)<8:return jsonify(error='Password must be at least 8 characters.'),400
    with db() as c: cur=c.execute("UPDATE users SET password_hash=%s,must_change_password=true WHERE id=%s AND role='student'",(generate_password_hash(pw),sid))
    if cur.rowcount==0:return jsonify(error='Student not found.'),404
    return {'ok':True}
@app.get('/api/attendance')
@login_required
def get_attendance():
    u=current_user(); params=[]; where=''
    if u['role']=='student':where='WHERE a.student_id=%s';params=[u['id']]
    with db() as c: rows=c.execute('SELECT a.id,a.student_id,u.full_name,a.attendance_date,a.status,a.note FROM attendance a JOIN users u ON u.id=a.student_id '+where+' ORDER BY attendance_date DESC LIMIT 500',params).fetchall()
    return {'records':rows}
@app.post('/api/attendance')
@admin_required
def mark_attendance():
    d=request.get_json() or {}; sid=d.get('student_id'); day=d.get('date') or date.today().isoformat(); status=d.get('status')
    if status not in ('present','absent'):return jsonify(error='Status must be present or absent.'),400
    with db() as c:c.execute('INSERT INTO attendance(student_id,attendance_date,status,note) VALUES(%s,%s,%s,%s) ON CONFLICT(student_id,attendance_date) DO UPDATE SET status=excluded.status,note=excluded.note',(sid,day,status,d.get('note','')))
    return {'ok':True}
@app.get('/api/materials')
@login_required
def materials():
    with db() as c:rows=c.execute('SELECT * FROM materials ORDER BY created_at DESC').fetchall()
    return {'materials':rows}
@app.post('/api/materials')
@admin_required
def add_material():
    d=request.get_json() or {}
    if not d.get('title') or not d.get('file_url'):return jsonify(error='Title and permanent file URL are required.'),400
    with db() as c:r=c.execute('INSERT INTO materials(title,subject,description,file_url) VALUES(%s,%s,%s,%s) RETURNING *',(d['title'],d.get('subject',''),d.get('description',''),d['file_url'])).fetchone()
    return {'material':r},201
@app.delete('/api/materials/<int:mid>')
@admin_required
def delete_material(mid):
    with db() as c:cur=c.execute('DELETE FROM materials WHERE id=%s',(mid,))
    return {'ok':cur.rowcount>0}
@app.get('/api/classes')
@login_required
def classes():
    with db() as c:rows=c.execute('SELECT * FROM classes ORDER BY starts_at DESC NULLS LAST').fetchall()
    return {'classes':rows}
@app.post('/api/classes')
@admin_required
def add_class():
    d=request.get_json() or {}
    if not d.get('title') or not d.get('class_url'):return jsonify(error='Title and class link are required.'),400
    with db() as c:r=c.execute('INSERT INTO classes(title,subject,class_url,starts_at,description) VALUES(%s,%s,%s,%s,%s) RETURNING *',(d['title'],d.get('subject',''),d['class_url'],d.get('starts_at') or None,d.get('description',''))).fetchone()
    return {'class':r},201
@app.get('/api/announcements')
@login_required
def announcements():
    with db() as c:rows=c.execute('SELECT * FROM announcements ORDER BY important DESC,created_at DESC').fetchall()
    return {'announcements':rows}
@app.post('/api/announcements')
@admin_required
def add_announcement():
    d=request.get_json() or {}
    if not d.get('title') or not d.get('body'):return jsonify(error='Title and message are required.'),400
    with db() as c:r=c.execute('INSERT INTO announcements(title,body,important) VALUES(%s,%s,%s) RETURNING *',(d['title'],d['body'],bool(d.get('important')))).fetchone()
    return {'announcement':r},201
@app.get('/api/tests')
@login_required
def tests():
    u=current_user()
    with db() as c:
        rows=c.execute("SELECT t.id,t.title,t.subject,t.duration_minutes,t.published,t.created_at,(SELECT count(*) FROM questions q WHERE q.test_id=t.id) question_count FROM tests t WHERE t.published=true OR %s='admin' ORDER BY t.created_at DESC",(u['role'],)).fetchall()
    return {'tests':rows}
@app.post('/api/tests')
@admin_required
def create_test():
    d=request.get_json() or {}
    if not d.get('title'):return jsonify(error='Test title is required.'),400
    questions=d.get('questions') or []
    if not questions:return jsonify(error='Add at least one question.'),400
    with db() as c:
        t=c.execute('INSERT INTO tests(title,subject,duration_minutes,published) VALUES(%s,%s,%s,%s) RETURNING id',(d['title'],d.get('subject',''),int(d.get('duration_minutes',30)),bool(d.get('published',False)))).fetchone()
        for q in questions:
            opts=q.get('options') or []
            if len(opts)!=4 or int(q.get('correct_index',-1)) not in range(4):raise ValueError('Every question needs exactly four options and a correct answer.')
            c.execute('INSERT INTO questions(test_id,question,options,correct_index,marks) VALUES(%s,%s,%s,%s,%s)',(t['id'],q['question'],psycopg.types.json.Json(opts),int(q['correct_index']),q.get('marks',1)))
    return {'id':t['id']},201
@app.get('/api/tests/<int:tid>')
@login_required
def test_detail(tid):
    u=current_user()
    with db() as c:
        t=c.execute('SELECT * FROM tests WHERE id=%s AND (published=true OR %s=\'admin\')',(tid,u['role'])).fetchone()
        if not t:return jsonify(error='Test not found.'),404
        qs=c.execute('SELECT id,question,options,marks FROM questions WHERE test_id=%s ORDER BY id',(tid,)).fetchall()
    return {'test':t,'questions':qs}
@app.post('/api/tests/<int:tid>/submit')
@login_required
def submit_test(tid):
    u=current_user()
    if u['role']!='student':return jsonify(error='Only students can submit tests.'),403
    answers=(request.get_json() or {}).get('answers') or {}
    with db() as c:
        if c.execute('SELECT id FROM submissions WHERE test_id=%s AND student_id=%s',(tid,u['id'])).fetchone():return jsonify(error='You have already submitted this test.'),409
        qs=c.execute('SELECT id,correct_index,marks FROM questions WHERE test_id=%s',(tid,)).fetchall()
        if not qs:return jsonify(error='Test has no questions.'),400
        score=sum(float(q['marks']) for q in qs if str(answers.get(str(q['id']),'x'))==str(q['correct_index']))
        c.execute('INSERT INTO submissions(test_id,student_id,answers,score) VALUES(%s,%s,%s,%s)',(tid,u['id'],psycopg.types.json.Json(answers),score))
    return {'score':score,'total':sum(float(q['marks']) for q in qs)}
@app.get('/api/results')
@login_required
def results():
    u=current_user(); where='WHERE s.student_id=%s' if u['role']=='student' else ''; params=[u['id']] if where else []
    with db() as c:rows=c.execute('SELECT s.id,t.title,t.subject,u.full_name,s.score,s.submitted_at FROM submissions s JOIN tests t ON t.id=s.test_id JOIN users u ON u.id=s.student_id '+where+' ORDER BY s.submitted_at DESC',params).fetchall()
    return {'results':rows}
@app.get('/api/fees')
@login_required
def fees():
    u=current_user(); where='WHERE f.student_id=%s' if u['role']=='student' else ''; params=[u['id']] if where else []
    with db() as c:rows=c.execute('SELECT f.*,u.full_name FROM fees f JOIN users u ON u.id=f.student_id '+where+' ORDER BY f.due_date DESC NULLS LAST',params).fetchall()
    return {'fees':rows}
@app.post('/api/fees')
@admin_required
def add_fee():
    d=request.get_json() or {}
    with db() as c:r=c.execute('INSERT INTO fees(student_id,amount,due_date,note) VALUES(%s,%s,%s,%s) RETURNING *',(d.get('student_id'),d.get('amount'),d.get('due_date') or None,d.get('note',''))).fetchone()
    return {'fee':r},201
@app.patch('/api/fees/<int:fid>')
@admin_required
def update_fee(fid):
    status=(request.get_json() or {}).get('status')
    if status not in ('paid','pending'):return jsonify(error='Invalid fee status.'),400
    with db() as c:cur=c.execute('UPDATE fees SET status=%s WHERE id=%s',(status,fid))
    return {'ok':cur.rowcount>0}
@app.get('/api/homework')
@login_required
def homework():
    with db() as c:rows=c.execute('SELECT * FROM homework ORDER BY due_date NULLS LAST').fetchall()
    return {'homework':rows}
@app.post('/api/homework')
@admin_required
def add_homework():
    d=request.get_json() or {}
    with db() as c:r=c.execute('INSERT INTO homework(title,description,due_date) VALUES(%s,%s,%s) RETURNING *',(d.get('title'),d.get('description',''),d.get('due_date') or None)).fetchone()
    return {'homework':r},201
@app.get('/api/export/attendance.csv')
@admin_required
def export_attendance():
    with db() as c:rows=c.execute('SELECT u.username,u.full_name,a.attendance_date,a.status,a.note FROM attendance a JOIN users u ON u.id=a.student_id ORDER BY attendance_date DESC').fetchall()
    out=io.StringIO(); w=csv.writer(out); w.writerow(['Username','Student','Date','Status','Note'])
    for r in rows:w.writerow([r['username'],r['full_name'],r['attendance_date'],r['status'],r['note']])
    return send_file(io.BytesIO(out.getvalue().encode('utf-8-sig')),mimetype='text/csv',as_attachment=True,download_name='rjvector-attendance.csv')
@app.errorhandler(500)
def server_error(e): return jsonify(error='Server error. Check Render logs; your saved database records are not intentionally deleted.'),500

with app.app_context(): init_db()
if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT',5000)))
