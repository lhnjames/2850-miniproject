import csv, os
from flask import Flask, request, redirect, session
from datetime import datetime

# ── PROXY PREFIX ──────────────────────────────────────────────────────────────
PREFIX = '/proxy/5050'

app = Flask(__name__)
app.secret_key = 'library-secret-key'

class PrefixMiddleware:
    def __init__(self, wsgi_app, prefix):
        self.app    = wsgi_app
        self.prefix = prefix
    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '/')
        if path.startswith(self.prefix):
            environ['PATH_INFO']   = path[len(self.prefix):] or '/'
            environ['SCRIPT_NAME'] = self.prefix
        return self.app(environ, start_response)

app.wsgi_app = PrefixMiddleware(app.wsgi_app, PREFIX)

# ── LOAD BOOKS FROM CSV ───────────────────────────────────────────────────────
# Reads library_booklist.csv from the same folder as this script.
# Deduplicates by (title, author) — keeps first occurrence location.

def _load_books():
    here    = os.path.dirname(os.path.abspath(__file__))
    csvpath = os.path.join(here, 'library_booklist.csv')
    seen    = {}
    bid     = 1
    with open(csvpath, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            title  = row['title'].strip()
            author = row['author'].strip()
            key    = (title, author)
            if key not in seen:
                isbn = row['isbn_13'].strip().rstrip('.0') if row['isbn_13'].strip() else ''
                loc  = row['location_code'].strip()
                seen[key] = {
                    'id': bid, 'title': title, 'author': author,
                    'isbn': isbn, 'location': loc, 'available': True,
                }
                bid += 1
    return list(seen.values()), bid   # books list, next_id

BOOKS, _next_book_id = _load_books()

# ── IN-MEMORY STATE ───────────────────────────────────────────────────────────
USERS         = {}   # { email: {name, password, address, is_staff} }
LOANS         = []   # [{id, book_id, book_title, user_email, user_name, borrowed_at, returned_at}]
NEXT_BOOK_ID  = [_next_book_id]
NEXT_LOAN_ID  = [1]

# ── STATE HELPERS ─────────────────────────────────────────────────────────────

def find_book(book_id):
    return next((b for b in BOOKS if b['id'] == book_id), None)

def active_loan(book_id):
    return next((l for l in LOANS
                 if l['book_id'] == book_id and l['returned_at'] is None), None)

def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M')

# ── HTML HELPERS ──────────────────────────────────────────────────────────────

def p(path=''):
    return PREFIX + path

def pop_flash():
    msg = session.pop('_flash', None)
    if not msg:
        return ''
    kind, text = msg[0], msg[2:]
    bg     = '#d4edda' if kind == 's' else '#f8d7da'
    color  = '#155724' if kind == 's' else '#721c24'
    border = '#c3e6cb' if kind == 's' else '#f5c6cb'
    return (f'<div style="padding:10px 16px;border-radius:6px;margin-bottom:14px;'
            f'background:{bg};color:{color};border:1px solid {border};">{text}</div>')

def set_flash(kind, msg):
    session['_flash'] = kind[0] + ':' + msg

def base(content, title='Library'):
    uid   = session.get('user_email')
    uname = session.get('user_name', '')
    staff = session.get('is_staff', False)

    if uid:
        staff_links = ''
        if staff:
            staff_links = (
                f'<a href="{p("/books/add")}" style="background:#97c93d;color:#1a3a1c;'
                f'padding:6px 14px;border-radius:4px;font-weight:600;text-decoration:none;'
                f'margin-left:1rem;">+ Add Book</a>'
                f'<a href="{p("/all-loans")}" style="color:white;text-decoration:none;'
                f'margin-left:1.5rem;opacity:.9;">All Loans</a>'
            )
        auth = (
            f'<a href="{p("/my-loans")}" style="color:white;text-decoration:none;'
            f'margin-left:1.5rem;opacity:.9;">My Loans</a>'
            f'{staff_links}'
            f'<a href="{p("/logout")}" style="color:white;text-decoration:none;'
            f'margin-left:1.5rem;opacity:.9;">Logout ({uname})</a>'
        )
    else:
        auth = (
            f'<a href="{p("/login")}" style="color:white;text-decoration:none;'
            f'margin-left:1.5rem;opacity:.9;">Login</a>'
            f'<a href="{p("/signup")}" style="background:#97c93d;color:#1a3a1c;'
            f'padding:6px 14px;border-radius:4px;font-weight:600;text-decoration:none;'
            f'margin-left:1rem;">Sign Up</a>'
        )

    role_badge = ''
    if staff:
        role_badge = ('<span style="background:#97c93d;color:#1a3a1c;padding:2px 8px;'
                      'border-radius:10px;font-size:.75rem;font-weight:700;'
                      'margin-left:.5rem;">STAFF</span>')

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:"Segoe UI",sans-serif;background:#f5f5f0;color:#333;font-size:16px}}
nav{{background:#2c5f2e;color:white;padding:0 2rem;display:flex;align-items:center;
     justify-content:space-between;min-height:60px;flex-wrap:wrap;gap:.5rem;
     box-shadow:0 2px 6px rgba(0,0,0,.3)}}
.brand{{font-size:1.3rem;font-weight:700;display:flex;align-items:center;gap:.4rem;padding:.5rem 0}}
.brand span{{color:#97c93d}}
.nav-right{{display:flex;align-items:center;flex-wrap:wrap;gap:.3rem;padding:.5rem 0}}
.container{{max-width:1200px;margin:2rem auto;padding:0 1.5rem}}
.card{{background:white;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.08);padding:2rem}}
.fg{{margin-bottom:1.2rem}}
.fg label{{display:block;font-weight:600;margin-bottom:5px;font-size:.95rem}}
.fg input[type=text],.fg input[type=email],.fg input[type=password]{{
  width:100%;padding:11px 13px;border:1px solid #ddd;border-radius:5px;font-size:1rem}}
.fg input:focus{{outline:none;border-color:#2c5f2e}}
.checkbox-row{{display:flex;align-items:center;gap:10px;padding:12px 14px;
               background:#f8f8f2;border:1px solid #ddd;border-radius:5px;margin-bottom:1.2rem}}
.checkbox-row input{{width:20px;height:20px;cursor:pointer;accent-color:#2c5f2e;flex-shrink:0}}
.checkbox-row label{{margin:0;font-size:.95rem;cursor:pointer}}
.btn{{padding:10px 22px;border:none;border-radius:5px;cursor:pointer;font-size:.95rem;
      font-weight:600;transition:opacity .2s;text-decoration:none;display:inline-block}}
.btn:hover{{opacity:.85}}
.btn-g{{background:#2c5f2e;color:white}}
.btn-b{{background:#2980b9;color:white}}
.btn-y{{background:#f0a500;color:white}}
.btn-r{{background:#c0392b;color:white}}
.btn-sm{{padding:6px 13px;font-size:.85rem}}
h1{{font-size:1.7rem;margin-bottom:1.5rem;color:#2c5f2e}}
a{{color:#2c5f2e}}
table{{width:100%;border-collapse:collapse}}
th,td{{padding:11px 14px;text-align:left;border-bottom:1px solid #eee;font-size:.92rem}}
th{{background:#f8f8f5;font-weight:600;color:#555}}
tr:hover td{{background:#fafaf7}}
footer{{text-align:center;padding:1.5rem;margin-top:3rem;color:#888;
        font-size:.85rem;border-top:1px solid #ddd}}
</style>
</head>
<body>
<nav>
  <div class="brand">&#128218; <span>Library</span>{role_badge}</div>
  <div class="nav-right">{auth}</div>
</nav>
<div class="container">
  <div style="margin-top:1rem">{pop_flash()}</div>
  {content}
</div>
<footer>Library System &copy; 2025 | COMP2850 Mini-Project</footer>
</body></html>'''


# ── HOME / CATALOGUE ──────────────────────────────────────────────────────────

@app.route('/')
def index():
    q          = request.args.get('q', '').strip()
    avail_only = request.args.get('avail', '') == '1'
    uid        = session.get('user_email')
    staff      = session.get('is_staff', False)

    books = BOOKS
    if q:
        ql    = q.lower()
        books = [b for b in books if ql in b['title'].lower() or ql in b['author'].lower()]
    if avail_only:
        books = [b for b in books if b['available']]

    # pagination — 24 per page
    page     = max(1, int(request.args.get('page', 1)))
    per_page = 24
    total    = len(books)
    pages    = max(1, (total + per_page - 1) // per_page)
    page     = min(page, pages)
    visible  = books[(page-1)*per_page : page*per_page]

    cards = ''
    for b in visible:
        bid  = b['id']
        loan = active_loan(bid)
        if b['available']:
            badge = ('<span style="background:#d4edda;color:#155724;padding:3px 10px;'
                     'border-radius:20px;font-size:.78rem;font-weight:600;">&#10003; Available</span>')
        else:
            who   = f' &mdash; {loan["user_name"]}' if loan else ''
            badge = (f'<span style="background:#f8d7da;color:#721c24;padding:3px 10px;'
                     f'border-radius:20px;font-size:.78rem;font-weight:600;">'
                     f'&#10007; On Loan{who}</span>')

        actions = ''
        if uid:
            if b['available']:
                actions += (f'<form action="{p(f"/books/borrow/{bid}")}" method="post" style="display:inline">'
                            f'<button class="btn btn-g btn-sm">Borrow</button></form> ')
            elif loan and loan['user_email'] == uid:
                actions += (f'<form action="{p(f"/books/return/{bid}")}" method="post" style="display:inline">'
                            f'<button class="btn btn-b btn-sm">Return</button></form> ')
            if staff:
                actions += (f'<a href="{p(f"/books/edit/{bid}")}" class="btn btn-y btn-sm">Edit</a> '
                            f'<form action="{p(f"/books/delete/{bid}")}" method="post" style="display:inline"'
                            f' onsubmit="return confirm(\'Delete this book?\')">'
                            f'<button class="btn btn-r btn-sm">Delete</button></form>')
        else:
            actions = f'<a href="{p("/login")}" class="btn btn-g btn-sm">Login to Borrow</a>'

        loc = b['location'] or '&mdash;'
        cards += f'''<div class="card" style="padding:1.1rem;position:relative;">
          <div style="position:absolute;top:10px;right:10px;">{badge}</div>
          <h2 style="font-size:1rem;margin-bottom:3px;padding-right:130px;line-height:1.35">{b["title"]}</h2>
          <p style="color:#555;font-size:.88rem;margin-bottom:6px;">by {b["author"]}</p>
          <p style="font-size:.8rem;color:#999;margin-bottom:10px;">&#128205; {loc}</p>
          <div style="display:flex;gap:7px;flex-wrap:wrap;">{actions}</div>
        </div>'''

    if not cards:
        cards = '<div class="card" style="text-align:center;padding:3rem;color:#888"><p>No books found.</p></div>'

    grid = (f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));'
            f'gap:1rem;">{cards}</div>')

    # pagination links
    def pg_url(n):
        parts = [f'page={n}']
        if q:          parts.append(f'q={q}')
        if avail_only: parts.append('avail=1')
        return p('/?' + '&'.join(parts))

    pagination = ''
    if pages > 1:
        prev_btn = (f'<a href="{pg_url(page-1)}" class="btn btn-sm" style="background:#eee;color:#333">'
                    f'&laquo; Prev</a>' if page > 1 else '')
        next_btn = (f'<a href="{pg_url(page+1)}" class="btn btn-sm" style="background:#eee;color:#333">'
                    f'Next &raquo;</a>' if page < pages else '')
        info = f'<span style="line-height:2.2;font-size:.9rem;color:#666">Page {page} / {pages}</span>'
        pagination = (f'<div style="display:flex;gap:8px;justify-content:center;'
                      f'align-items:center;margin-top:1.5rem;">{prev_btn}{info}{next_btn}</div>')

    avail_checked = 'checked' if avail_only else ''
    clear_btn = (f'<a href="{p("/")}" class="btn btn-sm" style="background:#eee;color:#333">Clear</a>'
                 if (q or avail_only) else '')
    top = f'''
    <div style="display:flex;justify-content:space-between;align-items:flex-start;
                margin-bottom:1.5rem;flex-wrap:wrap;gap:1rem;">
      <div>
        <h1 style="margin-bottom:.3rem">&#128214; Book Catalogue</h1>
        <p style="color:#666;font-size:.9rem">{total} book{"s" if total!=1 else ""} found
          &nbsp;&middot;&nbsp; Page {page} of {pages}</p>
      </div>
      <form action="{p("/")}" method="get"
            style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
        <input name="q" placeholder="Search title or author..."
               value="{q}"
               style="padding:9px 14px;border:1px solid #ddd;border-radius:5px;
                      width:230px;font-size:.95rem">
        <label style="display:flex;align-items:center;gap:6px;font-size:.9rem;cursor:pointer;white-space:nowrap">
          <input type="checkbox" name="avail" value="1" {avail_checked}
                 style="accent-color:#2c5f2e;width:16px;height:16px">
          Available only
        </label>
        <button type="submit" class="btn btn-g btn-sm">Search</button>
        {clear_btn}
      </form>
    </div>'''

    return base(top + grid + pagination)


# ── BORROW ────────────────────────────────────────────────────────────────────

@app.route('/books/borrow/<int:book_id>', methods=['POST'])
def borrow_book(book_id):
    if 'user_email' not in session:
        set_flash('error', 'Please log in to borrow books.')
        return redirect(p('/login'))
    book = find_book(book_id)
    if not book:
        set_flash('error', 'Book not found.')
    elif not book['available']:
        set_flash('error', 'This book is currently on loan.')
    else:
        book['available'] = False
        LOANS.append({
            'id':          NEXT_LOAN_ID[0],
            'book_id':     book_id,
            'book_title':  book['title'],
            'user_email':  session['user_email'],
            'user_name':   session['user_name'],
            'borrowed_at': now(),
            'returned_at': None,
        })
        NEXT_LOAN_ID[0] += 1
        set_flash('success', f'You have borrowed &ldquo;{book["title"]}&rdquo;!')
    return redirect(request.referrer or p('/'))


# ── RETURN ────────────────────────────────────────────────────────────────────

@app.route('/books/return/<int:book_id>', methods=['POST'])
def return_book(book_id):
    if 'user_email' not in session:
        set_flash('error', 'Please log in.')
        return redirect(p('/login'))
    book = find_book(book_id)
    loan = active_loan(book_id)
    if not book or not loan:
        set_flash('error', 'No active loan found for this book.')
    elif loan['user_email'] != session['user_email']:
        set_flash('error', 'You did not borrow this book.')
    else:
        book['available']   = True
        loan['returned_at'] = now()
        set_flash('success', f'You have returned &ldquo;{book["title"]}&rdquo;. Thank you!')
    return redirect(request.referrer or p('/'))


# ── MY LOANS ──────────────────────────────────────────────────────────────────

@app.route('/my-loans')
def my_loans():
    if 'user_email' not in session:
        set_flash('error', 'Please log in.')
        return redirect(p('/login'))
    email = session['user_email']
    my    = [l for l in LOANS if l['user_email'] == email]

    rows = ''
    for l in reversed(my):
        if l['returned_at']:
            status  = f'&#10003; Returned<br><small style="color:#888">{l["returned_at"]}</small>'
            ret_btn = ''
        else:
            status  = '<span style="color:#c0392b;font-weight:600">On Loan</span>'
            ret_btn = (f'<form action="{p(f"/books/return/{l[chr(98)+chr(111)+chr(111)+chr(107)+chr(95)+chr(105)+chr(100)]}")}"'
                       f' method="post" style="display:inline">'
                       f'<button class="btn btn-b btn-sm">Return</button></form>')
        rows += (f'<tr><td>{l["book_title"]}</td>'
                 f'<td>{l["borrowed_at"]}</td>'
                 f'<td>{status}</td>'
                 f'<td>{ret_btn}</td></tr>')

    if not rows:
        rows = '<tr><td colspan="4" style="text-align:center;color:#888;padding:2rem">No borrowing history yet.</td></tr>'

    content = f'''
    <h1>&#128196; My Loans</h1>
    <div class="card" style="padding:0;overflow:hidden">
      <table>
        <thead><tr><th>Book</th><th>Borrowed</th><th>Status</th><th>Action</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    <p style="margin-top:1rem"><a href="{p("/")}">&#8592; Back to catalogue</a></p>'''
    return base(content, 'My Loans')


# ── ALL LOANS (staff only) ────────────────────────────────────────────────────

@app.route('/all-loans')
def all_loans():
    if not session.get('is_staff'):
        set_flash('error', 'Staff access required.')
        return redirect(p('/'))
    rows = ''
    for l in reversed(LOANS):
        status = (f'Returned {l["returned_at"]}' if l['returned_at']
                  else '<span style="color:#c0392b;font-weight:600">On Loan</span>')
        rows += (f'<tr><td>{l["book_title"]}</td>'
                 f'<td>{l["user_name"]}<br><small style="color:#888">{l["user_email"]}</small></td>'
                 f'<td>{l["borrowed_at"]}</td>'
                 f'<td>{status}</td></tr>')
    if not rows:
        rows = '<tr><td colspan="4" style="text-align:center;color:#888;padding:2rem">No loans recorded yet.</td></tr>'

    content = f'''
    <h1>&#128203; All Loan Records</h1>
    <div class="card" style="padding:0;overflow:hidden">
      <table>
        <thead><tr><th>Book</th><th>Borrower</th><th>Borrowed</th><th>Status</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    <p style="margin-top:1rem"><a href="{p("/")}">&#8592; Back to catalogue</a></p>'''
    return base(content, 'All Loans')


# ── SIGN UP ───────────────────────────────────────────────────────────────────

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name     = request.form.get('name', '').strip()
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        address  = request.form.get('address', '').strip()
        is_staff = bool(request.form.get('is_staff'))
        if not all([name, email, password, address]):
            set_flash('error', 'All fields are required.')
            return redirect(p('/signup'))
        if email in USERS:
            set_flash('error', 'Email already registered.')
            return redirect(p('/signup'))
        USERS[email] = {'name': name, 'password': password,
                        'address': address, 'is_staff': is_staff}
        role = 'Staff account' if is_staff else 'Account'
        set_flash('success', f'{role} created for {name}! Please log in.')
        return redirect(p('/login'))

    content = f'''
    <div style="max-width:480px;margin:0 auto"><div class="card">
      <h1>Create an Account</h1>
      <p style="color:#666;margin-bottom:1.5rem;font-size:.95rem">Sign up to borrow books from the library</p>
      <form method="post" action="{p("/signup")}">
        <div class="fg"><label>Full Name *</label>
          <input type="text" name="name" placeholder="e.g. Margaret Johnson" required></div>
        <div class="fg"><label>Email Address *</label>
          <input type="email" name="email" placeholder="e.g. margaret@example.com" required></div>
        <div class="fg"><label>Password *</label>
          <input type="password" name="password" placeholder="Choose a password" required></div>
        <div class="fg"><label>Home Address *</label>
          <input type="text" name="address" placeholder="e.g. 12 Park Lane, LS1 1AA" required></div>
        <div class="checkbox-row">
          <input type="checkbox" name="is_staff" id="is_staff" value="1">
          <label for="is_staff">
            <strong>Register as Staff</strong> &mdash; can add, edit and delete books
          </label>
        </div>
        <button type="submit" class="btn btn-g" style="width:100%">Create Account</button>
      </form>
      <p style="text-align:center;margin-top:1rem;font-size:.9rem;color:#666">
        Already have an account? <a href="{p("/login")}">Log in here</a></p>
    </div></div>'''
    return base(content, 'Sign Up')


# ── LOGIN ─────────────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user     = USERS.get(email)
        if user and user['password'] == password:
            session['user_email'] = email
            session['user_name']  = user['name']
            session['is_staff']   = user['is_staff']
            set_flash('success', f'Welcome back, {user["name"]}!')
            return redirect(p('/'))
        set_flash('error', 'Invalid email or password.')
        return redirect(p('/login'))

    content = f'''
    <div style="max-width:420px;margin:0 auto"><div class="card">
      <h1>Log In</h1>
      <p style="color:#666;margin-bottom:1.5rem;font-size:.95rem">Welcome back to the Library</p>
      <form method="post" action="{p("/login")}">
        <div class="fg"><label>Email Address</label>
          <input type="email" name="email" placeholder="your@email.com" required></div>
        <div class="fg"><label>Password</label>
          <input type="password" name="password" placeholder="Your password" required></div>
        <button type="submit" class="btn btn-g" style="width:100%">Log In</button>
      </form>
      <p style="text-align:center;margin-top:1rem;font-size:.9rem;color:#666">
        Don&apos;t have an account? <a href="{p("/signup")}">Sign up here</a></p>
    </div></div>'''
    return base(content, 'Login')


# ── LOGOUT ────────────────────────────────────────────────────────────────────

@app.route('/logout')
def logout():
    session.clear()
    set_flash('success', 'You have been logged out.')
    return redirect(p('/'))


# ── ADD BOOK (staff only) ─────────────────────────────────────────────────────

@app.route('/books/add', methods=['GET', 'POST'])
def add_book():
    if not session.get('is_staff'):
        set_flash('error', 'Staff access required.')
        return redirect(p('/'))
    if request.method == 'POST':
        title    = request.form.get('title', '').strip()
        author   = request.form.get('author', '').strip()
        isbn     = request.form.get('isbn', '').strip()
        location = request.form.get('location', '').strip()
        if not title or not author:
            set_flash('error', 'Title and author are required.')
            return redirect(p('/books/add'))
        BOOKS.append({
            'id': NEXT_BOOK_ID[0], 'title': title, 'author': author,
            'isbn': isbn, 'location': location, 'available': True,
        })
        NEXT_BOOK_ID[0] += 1
        set_flash('success', f'Book &ldquo;{title}&rdquo; added successfully!')
        return redirect(p('/'))

    content = f'''
    <div style="max-width:560px;margin:0 auto"><div class="card">
      <h1>Add New Book</h1>
      <p style="color:#666;margin-bottom:1.5rem;font-size:.95rem">Add a book to the library catalogue</p>
      <form method="post" action="{p("/books/add")}">
        <div class="fg"><label>Title *</label>
          <input type="text" name="title" placeholder="e.g. The Midnight Library" required></div>
        <div class="fg"><label>Author *</label>
          <input type="text" name="author" placeholder="e.g. Matt Haig" required></div>
        <div class="fg"><label>ISBN</label>
          <input type="text" name="isbn" placeholder="e.g. 9780525559474"></div>
        <div class="fg"><label>Shelf Location</label>
          <input type="text" name="location" placeholder="e.g. F1-B03-S05"></div>
        <div style="display:flex;gap:1rem;margin-top:.5rem">
          <button type="submit" class="btn btn-g">Add Book</button>
          <a href="{p("/")}" style="line-height:2.4;color:#666;text-decoration:none">Cancel</a>
        </div>
      </form>
    </div></div>'''
    return base(content, 'Add Book')


# ── EDIT BOOK (staff only) ────────────────────────────────────────────────────

@app.route('/books/edit/<int:book_id>', methods=['GET', 'POST'])
def edit_book(book_id):
    if not session.get('is_staff'):
        set_flash('error', 'Staff access required.')
        return redirect(p('/'))
    book = find_book(book_id)
    if not book:
        set_flash('error', 'Book not found.')
        return redirect(p('/'))
    if request.method == 'POST':
        title  = request.form.get('title', '').strip()
        author = request.form.get('author', '').strip()
        if not title or not author:
            set_flash('error', 'Title and author are required.')
            return redirect(p(f'/books/edit/{book_id}'))
        book['title']    = title
        book['author']   = author
        book['isbn']     = request.form.get('isbn', '').strip()
        book['location'] = request.form.get('location', '').strip()
        set_flash('success', f'Book &ldquo;{title}&rdquo; updated!')
        return redirect(p('/'))

    content = f'''
    <div style="max-width:560px;margin:0 auto"><div class="card">
      <h1>Edit Book</h1>
      <p style="color:#666;margin-bottom:1.5rem;font-size:.95rem">Update the details for this book</p>
      <form method="post" action="{p(f'/books/edit/{book_id}')}">
        <div class="fg"><label>Title *</label>
          <input type="text" name="title" value="{book['title']}" required></div>
        <div class="fg"><label>Author *</label>
          <input type="text" name="author" value="{book['author']}" required></div>
        <div class="fg"><label>ISBN</label>
          <input type="text" name="isbn" value="{book.get('isbn','') or ''}"></div>
        <div class="fg"><label>Shelf Location</label>
          <input type="text" name="location" value="{book.get('location','') or ''}"></div>
        <div style="display:flex;gap:1rem">
          <button type="submit" class="btn btn-g">Save Changes</button>
          <a href="{p("/")}" style="line-height:2.4;color:#666;text-decoration:none">Cancel</a>
        </div>
      </form>
    </div></div>'''
    return base(content, 'Edit Book')


# ── DELETE BOOK (staff only) ──────────────────────────────────────────────────

@app.route('/books/delete/<int:book_id>', methods=['POST'])
def delete_book(book_id):
    if not session.get('is_staff'):
        set_flash('error', 'Staff access required.')
        return redirect(p('/'))
    book = find_book(book_id)
    if book:
        BOOKS.remove(book)
        set_flash('success', f'Book &ldquo;{book["title"]}&rdquo; deleted.')
    return redirect(p('/'))


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print(f'Loaded {len(BOOKS)} books from library_booklist.csv')
    app.run(debug=True, port=5050)