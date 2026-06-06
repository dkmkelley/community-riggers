from datetime import date, timedelta
from functools import wraps
import os

from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash

from database import get_db, generate_token

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("AUTH0_SECRET")
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False

oauth = OAuth(app)
oauth.register(
    "auth0",
    client_id=os.getenv("AUTH0_CLIENT_ID"),
    client_secret=os.getenv("AUTH0_CLIENT_SECRET"),
    client_kwargs={"scope": "openid profile email"},
    server_metadata_url=f'https://{os.getenv("AUTH0_DOMAIN")}/.well-known/openid-configuration'
)


def is_admin():
    return session.get('user') is not None


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_admin():
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_user():
    return dict(current_user=session.get('user'))


# Filter function to normalize phone numbers to a standard format (XXX) XXX-XXXX
@app.template_filter("format_phone")
def format_phone(phone):
    if not phone:
        return "—"
    digits = ''.join(filter(str.isdigit, phone))
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    elif len(digits) == 11 and digits[0] == '1':
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    return phone


# Default route. Currently redirects to the list of riggers
@app.route("/")
def home():
    return redirect(url_for("list_riggers"))


# auth0 login route
@app.route("/login")
def login():
    return oauth.auth0.authorize_redirect(redirect_uri=url_for("callback", _external=True))


# auth0 callback route
@app.route("/callback")
def callback():
    token = oauth.auth0.authorize_access_token()
    session["user"] = token
    return redirect(url_for("admin_availability"))


# auth0 logout route
@app.route("/logout")
def logout():
    session.clear()
    return redirect(
        f'https://{os.getenv("AUTH0_DOMAIN")}/v2/logout?'
        f'returnTo={url_for("home", _external=True)}&'
        f'client_id={os.getenv("AUTH0_CLIENT_ID")}'
    )


# Route to list all riggers
@app.route("/riggers")
@admin_required
def list_riggers():
    conn = get_db()
    
    riggers = conn.execute("SELECT id, name, phone, affiliation, city, token FROM riggers WHERE status = 'approved'"
    ).fetchall()
    riggers = sorted(riggers, key=lambda r: r['name'].split()[-1].lower())  # Sort by last name, case-insensitive
    conn.close()
    
    print(f"DEBUG: {len(riggers)} riggers found")
    for r in riggers:
        print(f"DEBUG: {r['name']} - {r['status'] if 'status' in r.keys() else 'no status'}")
    return render_template("riggers.html", riggers=riggers)


# Route to add a new rigger
@app.route("/add", methods=["GET", "POST"])
def add_rigger():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        affiliation = request.form.get("affiliation", "").strip()
        city = request.form.get("city", "").strip()

        if not name or not phone:
            return render_template("add_rigger.html", error="Name and phone are required.")
        
        digits = ''.join(filter(str.isdigit, phone))
        if len(digits) == 10:
            phone = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        elif len(digits) == 11 and digits[0] == '1':
            phone = f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
        else:
            return render_template("add_rigger.html", error="Please enter a valid 10-digit phone number.")

        token = generate_token()

        conn = get_db()
        conn.execute(
            "INSERT INTO riggers (name, phone, affiliation, city, token) VALUES (?, ?, ?, ?, ?)",
            (name, phone, affiliation or None, city or None, token)
        )
        conn.commit()
        conn.close()

        flash(f"Welcome, {name}! You've been added to the directory. "
              " Your profile is pending admin approval and will appear in the directory shortly."
              " Bookmark this page — it's your personal link for updating your availability. "
              " There is no login information or password to remember, just the link."
              " You can set your availability for the next 5 days using the buttons on this page."
              " This system can only be useful if you keep your availability up to date:"
              " If your availability changes, please update it."
        )
        
        return redirect(url_for("availability", token=token))

    return render_template("add_rigger.html")


# Route to edit an existing rigger
@app.route("/riggers/<int:id>/edit", methods=["GET", "POST"])
@admin_required
def edit_rigger(id):
    conn = get_db()
    rigger = conn.execute(
        "SELECT * FROM riggers WHERE id = ?", (id,)).fetchone()

    if rigger is None:
        conn.close()
        return "Rigger not found.", 404

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        affiliation = request.form.get("affiliation", "").strip()
        city = request.form.get("city", "").strip()

        if not name or not phone:
            conn.close()
            return render_template("edit_rigger.html", rigger=rigger, error="Name and phone are required.")
        
        digits = ''.join(filter(str.isdigit, phone))
        if len(digits) == 10:
            phone = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        elif len(digits) == 11 and digits[0] == '1':
            phone = f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
        else:
            return render_template("edit_rigger.html", rigger=rigger, error="Please enter a valid 10-digit phone number.")

        conn.execute(
            """UPDATE riggers
               SET name = ?, phone = ?, affiliation = ?, city = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (name, phone, affiliation or None, city or None, id)
        )
        conn.commit()
        conn.close()
        return redirect(url_for("list_riggers"))

    conn.close()
    return render_template("edit_rigger.html", rigger=rigger)


# Route to delete a rigger
@app.route("/riggers/<int:id>/delete", methods=["GET", "POST"])
@admin_required
def delete_rigger(id):
    conn = get_db()
    rigger = conn.execute(
        "SELECT * FROM riggers WHERE id = ?", (id,)
    ).fetchone()

    if rigger is None:
        conn.close()
        return "Rigger not found.", 404

    if request.method == "POST":
        conn.execute("DELETE FROM riggers WHERE id = ?", (id,))
        conn.commit()
        conn.close()
        return redirect(url_for("list_riggers"))

    conn.close()
    return render_template("delete_rigger.html", rigger=rigger)


# Admin view to see all riggers and their availability for the next 5 days. Is public on dev server but should be protected in production.
@app.route("/admin/availability")
@admin_required
def admin_availability():
    conn = get_db()
    
    filter_day = request.args.get('filter_day', 'all') # Get the filter_day parameter from the query string, default to 'all'

    days = []
    for i in range(5):
        d = date.today() + timedelta(days=i)
        days.append({
            "date_str": d.strftime("%b %d"),
            "date_val": d.strftime("%Y-%m-%d")
        })

    # Determine the date filter based on the filter_day parameter
    if filter_day == 'all':
        date_filter = None # No date filter, show all riggers
    elif filter_day == 'today':
        date_filter = date.today().strftime("%Y-%m-%d") # Filter for riggers available today
    elif filter_day == 'tomorrow':
        date_filter = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d") # Filter for riggers available tomorrow
    else:
        date_filter = filter_day  # Assume it's in YYYY-MM-DD format


    # If a date filter is applied, modify the query to only include riggers available on that date
    if date_filter:
        rows = conn.execute("""
            SELECT r.id, r.name, r.phone, r.affiliation, r.city,
                   MAX(CASE WHEN a.date = date('now') THEN 1 ELSE 0 END) as day_0,
                   MAX(CASE WHEN a.date = date('now', '+1 days') THEN 1 ELSE 0 END) as day_1,
                   MAX(CASE WHEN a.date = date('now', '+2 days') THEN 1 ELSE 0 END) as day_2,
                   MAX(CASE WHEN a.date = date('now', '+3 days') THEN 1 ELSE 0 END) as day_3,
                   MAX(CASE WHEN a.date = date('now', '+4 days') THEN 1 ELSE 0 END) as day_4
            FROM riggers r
            LEFT JOIN availability a ON a.rigger_id = r.id
            WHERE r.status = 'approved'
            AND r.id IN (
                SELECT rigger_id FROM availability WHERE date =?
            )
            GROUP BY r.id
        """, (date_filter,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT r.id, r.name, r.phone, r.affiliation, r.city,
               MAX(CASE WHEN a.date = date('now') THEN 1 ELSE 0 END) as day_0,
               MAX(CASE WHEN a.date = date('now', '+1 days') THEN 1 ELSE 0 END) as day_1,
               MAX(CASE WHEN a.date = date('now', '+2 days') THEN 1 ELSE 0 END) as day_2,
               MAX(CASE WHEN a.date = date('now', '+3 days') THEN 1 ELSE 0 END) as day_3,
               MAX(CASE WHEN a.date = date('now', '+4 days') THEN 1 ELSE 0 END) as day_4
            FROM riggers r
            LEFT JOIN availability a ON a.rigger_id = r.id
            WHERE r.status = 'approved'
            GROUP BY r.id
        """).fetchall()

    # Process the rows into a list of riggers with their availability
    riggers = []
    for r in rows:
        riggers.append({
            "id": r["id"],
            "name": r["name"],
            "phone": r["phone"],            
            "availability": [r["day_0"], r["day_1"], r["day_2"], r["day_3"], r["day_4"]]
        })

    riggers = sorted(riggers, key=lambda r: r['name'].split()[-1].lower()) # Sort by last name, case-insensitive
    conn.close()
    return render_template("admin_availability.html", riggers=riggers, days=days, filter_day=filter_day)


# Admin view to see all riggers with status of 'pending'. Is public on dev server but should be protected in production.
@app.route("/admin/pending")
@admin_required
def admin_pending():
    conn = get_db()
    riggers = conn.execute("SELECT * FROM riggers WHERE status = 'pending' ORDER BY created_at").fetchall()
    conn.close()
    return render_template("admin_pending.html", riggers=riggers)

# Admin route to add a rigger on their behalf
@app.route("/admin/add", methods=["GET", "POST"])
@admin_required
def admin_add_rigger():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        affiliation = request.form.get("affiliation", "").strip()
        city = request.form.get("city", "").strip()

        if not name or not phone:
            return render_template("add_rigger.html", error="Name and phone are required.")

        digits = ''.join(filter(str.isdigit, phone))
        if len(digits) == 10:
            phone = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        elif len(digits) == 11 and digits[0] == '1':
            phone = f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
        else:
            return render_template("add_rigger.html",
                                   error="Please enter a valid 10-digit phone number.")

        token = generate_token()

        conn = get_db()
        conn.execute(
            "INSERT INTO riggers (name, phone, affiliation, city, token) VALUES (?, ?, ?, ?, ?)",
            (name, phone, affiliation or None, city or None, token)
        )
        conn.commit()
        conn.close()

        return redirect(url_for("admin_pending"))

    return render_template("add_rigger.html")


# Admin approval action to set a rigger's status to 'approved'. Is public on dev server but should be protected in production.
@app.route("/admin/pending/<int:id>/approve", methods=["POST"])
@admin_required
def approve_rigger(id):
    conn = get_db()
    conn.execute(
        "UPDATE riggers SET status = 'approved', updated_at = datetime('now') WHERE id = ?",
        (id,)
    )
    conn.commit()
    conn.close()
    return redirect(url_for("admin_pending"))


# Admin rejection route. Also removes the rigger from the database. Is public on dev server but should be protected in production.
@app.route("/admin/pending/<int:id>/reject", methods=["POST"])
@admin_required
def reject_rigger(id):
    conn = get_db()
    conn.execute("DELETE FROM riggers WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_pending"))


# Route for riggers to set their availability for the next 5 days using a unique token link.
@app.route("/availability/<token>", methods=["GET", "POST"])
def availability(token):
    conn = get_db()
    rigger = conn.execute("SELECT * FROM riggers WHERE token = ?", (token,)).fetchone()

    if rigger is None:
        conn.close()
        return "Invalid link.", 404

    if request.method == "POST":
        try:
            offset = int(request.form.get("day", -1))
        except ValueError:
            conn.close()
            return "Invalid request.", 400

        if offset not in range(5):
            conn.close()
            return "Invalid request.", 400

        modifier = f"+{offset} days"
        existing = conn.execute(
            "SELECT id FROM availability WHERE rigger_id = ? AND date = date('now', ?)",
            (rigger["id"], modifier)
        ).fetchone()

        if existing:
            conn.execute(
                "DELETE FROM availability WHERE rigger_id = ? AND date = date('now', ?)",
                (rigger["id"], modifier)
            )
        else:
            conn.execute(
                "INSERT INTO availability (rigger_id, date) VALUES (?, date('now', ?))",
                (rigger["id"], modifier)
            )

        conn.commit()
        conn.close()
        return redirect(url_for("availability", token=token))

    days = []
    for i in range(5):
        modifier = f"+{i} days"
        d = date.today() + timedelta(days=i)
        available = conn.execute(
            "SELECT id FROM availability WHERE rigger_id = ? AND date = date('now', ?)",
            (rigger["id"], modifier)
        ).fetchone() is not None

        if i == 0:
            label = "Today"
        elif i == 1:
            label = "Tomorrow"
        else:
            label = d.strftime("%A")

        days.append({
            "offset": i,
            "label": label,
            "date_str": d.strftime("%B %d, %Y"),
            "available": available
        })

    conn.close()
    return render_template("availability.html",
                           rigger=rigger,
                           days=days)


# Route for riggers to edit their own information using a unique token link. Separate from the admin edit route.

@app.route("/availability/<token>/edit", methods=["GET", "POST"])
def edit_own_info(token):
    conn = get_db()
    rigger = conn.execute(
        "SELECT * FROM riggers WHERE token = ?", (token,)
    ).fetchone()

    if rigger is None:
        conn.close()
        return "Invalid link.", 404

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        affiliation = request.form.get("affiliation", "").strip()
        city = request.form.get("city", "").strip()

        if not name or not phone:
            conn.close()
            return render_template("edit_own_info.html", rigger=rigger,
                       error="Name and phone are required.", current_user=None)

        digits = ''.join(filter(str.isdigit, phone))
        if len(digits) == 10:
            phone = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        elif len(digits) == 11 and digits[0] == '1':
            phone = f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
        else:
            return render_template("edit_own_info.html", rigger=rigger,
                       error="Please enter a valid 10-digit US phone number.", current_user=None)

        conn.execute(
            """UPDATE riggers
               SET name = ?, phone = ?, affiliation = ?, city = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (name, phone, affiliation or None, city or None, rigger["id"])
        )
        conn.commit()
        conn.close()
        return redirect(url_for("availability", token=token))

    conn.close()
    return render_template("edit_own_info.html", rigger=rigger, current_user=None)






if __name__ == "__main__":
    app.run(debug=True)