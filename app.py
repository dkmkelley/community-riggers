from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from functools import wraps
import os

from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from database import get_db, generate_token, ensure_schema

load_dotenv()
ensure_schema()

# Helper function to set the timezone to Pacific Time for all date operations instead of relying on server's timezone

def pacific_today():
    return datetime.now(ZoneInfo("America/Los_Angeles")).date()

# Flask application setup
app = Flask(__name__)
app.secret_key = os.getenv("AUTH0_SECRET")
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False


@app.context_processor
def inject_asset_version():
    def asset_url(filename):
        filepath = os.path.join(app.static_folder, filename)
        version = int(os.path.getmtime(filepath))
        return url_for('static', filename=filename) + f'?v={version}'
    return dict(asset_url=asset_url)


# OAuth setup for Auth0

oauth = OAuth(app)
oauth.register(
    "auth0",
    client_id=os.getenv("AUTH0_CLIENT_ID"),
    client_secret=os.getenv("AUTH0_CLIENT_SECRET"),
    client_kwargs={"scope": "openid profile email"},
    server_metadata_url=f'https://{os.getenv("AUTH0_DOMAIN")}/.well-known/openid-configuration'
)


# Twilio setup for sending SMS messages from the server

twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
TWILIO_MESSAGING_SERVICE_SID = os.getenv("TWILIO_MESSAGING_SERVICE_SID")


# Converts a stored phone number into E.164 format (e.g. +14155551234) as required by Twilio
def to_e164(phone):
    digits = ''.join(filter(str.isdigit, phone))
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits[0] == '1':
        return f"+{digits}"
    return None


# Sends a single SMS via Twilio. Returns True on success, False if the send failed.
def send_sms(phone, body):
    to_number = to_e164(phone)
    if not to_number:
        return False
    try:
        twilio_client.messages.create(body=body, messaging_service_sid=TWILIO_MESSAGING_SERVICE_SID, to=to_number)
        return True
    except TwilioRestException:
        return False


# Helper functions for authentication and authorization

# Check if the user is logged in (admin)
def is_admin():
    return session.get('user') is not None

# Decorator to require admin login for certain routes
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_admin():
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Inject the current user into the template context for use in templates
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


# Filter function to display a full name as "Last, First"
@app.template_filter("last_first")
def last_first(name):
    parts = name.split()
    if len(parts) < 2:
        return name
    return f"{parts[-1]}, {' '.join(parts[:-1])}"


# Default route. Currently redirects to the admin availability page if logged in, otherwise shows a landing page

@app.route("/")
def home():
    if is_admin():
        return redirect(url_for("admin_availability"))
    return render_template("landing.html")


# Public terms of service and privacy policy pages, linked from the SMS consent checkbox on the sign-up form

@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


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


# Route to list all riggers in the riggers directory. Only accessible to admins. Riggers are sorted by first name, case-insensitive.

@app.route("/riggers")
@admin_required
def list_riggers():
    conn = get_db()

    sort_by = request.args.get('sort_by', 'name')
    sort_dir = request.args.get('sort_dir', 'asc')

    riggers = conn.execute("SELECT id, name, phone, affiliation, city, token, sms_consent FROM riggers WHERE status = 'approved'"
    ).fetchall()

    if sort_by == 'city':
        riggers = sorted(riggers, key=lambda r: (r['city'] or '').lower(), reverse=(sort_dir == 'desc'))
    else:
        riggers = sorted(riggers, key=lambda r: r['name'].split()[-1].lower(), reverse=(sort_dir == 'desc'))  # Sort by last name, case-insensitive

    conn.close()

    return render_template("riggers.html", riggers=riggers, sort_by=sort_by, sort_dir=sort_dir)


# Sends an SMS message (via Twilio) to one or more selected riggers. Used for both single-rigger
# canned messages (e.g. "Send Link" buttons) and the multi-select bulk message form.
@app.route("/admin/send_sms", methods=["POST"])
@admin_required
def admin_send_sms():
    rigger_ids = request.form.getlist("rigger_ids")
    message = request.form.get("message", "").strip()

    if not rigger_ids:
        flash("No riggers selected.")
        return redirect(request.referrer or url_for("admin_availability"))
    if not message:
        flash("Message cannot be empty.")
        return redirect(request.referrer or url_for("admin_availability"))

    conn = get_db()
    placeholders = ",".join("?" * len(rigger_ids))
    riggers = conn.execute(
        f"SELECT phone, sms_consent FROM riggers WHERE id IN ({placeholders})", rigger_ids
    ).fetchall()
    conn.close()

    consented = [r for r in riggers if r["sms_consent"]]
    skipped = len(riggers) - len(consented)

    sent = sum(1 for r in consented if send_sms(r["phone"], message))
    failed = len(consented) - sent

    parts = [f"Sent to {sent} rigger(s)."]
    if failed:
        parts.append(f"{failed} failed to send.")
    if skipped:
        parts.append(f"{skipped} skipped (no SMS consent on file).")
    flash(" ".join(parts))

    return redirect(request.referrer or url_for("admin_availability"))


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

        sms_consent = 1 if request.form.get("sms_consent") else 0

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
            "INSERT INTO riggers (name, phone, affiliation, city, token, sms_consent) VALUES (?, ?, ?, ?, ?, ?)",
            (name, phone, affiliation or None, city or None, token, sms_consent)
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

        sms_consent = 1 if request.form.get("sms_consent") else 0

        conn.execute(
            """UPDATE riggers
               SET name = ?, phone = ?, affiliation = ?, city = ?, sms_consent = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (name, phone, affiliation or None, city or None, sms_consent, id)
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
    sort_by = request.args.get('sort_by', 'name')
    # Default direction depends on the field: A-Z for name, most-recently-updated-first for last_updated.
    # Only falls back to this when sort_dir isn't explicitly in the URL (e.g. from the Name column header link).
    sort_dir = request.args.get('sort_dir') or ('desc' if sort_by == 'last_updated' else 'asc')

    days = []
    for i in range(5):
        d = pacific_today() + timedelta(days=i)
        days.append({
            "date_str": d.strftime("%b %d"),
            "date_val": d.strftime("%Y-%m-%d")
        })

    # Determine the date filter based on the filter_day parameter
    if filter_day == 'all':
        date_filter = None # No date filter, show all riggers
    elif filter_day == 'today':
        date_filter = pacific_today().strftime("%Y-%m-%d") # Filter for riggers available today
    elif filter_day == 'tomorrow':
        date_filter = (pacific_today() + timedelta(days=1)).strftime("%Y-%m-%d") # Filter for riggers available tomorrow
    else:
        date_filter = filter_day  # Assume it's in YYYY-MM-DD format

    day_strs = [(pacific_today() + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(5)]

    # If a date filter is applied, modify the query to only include riggers available on that date
    if date_filter:
        rows = conn.execute("""
            SELECT r.id, r.name, r.phone, r.affiliation, r.city, r.token, r.last_toggled_at, r.sms_consent,
                MAX(CASE WHEN a.date = ? THEN 1 ELSE 0 END) as day_0,
                MAX(CASE WHEN a.date = ? THEN 1 ELSE 0 END) as day_1,
                MAX(CASE WHEN a.date = ? THEN 1 ELSE 0 END) as day_2,
                MAX(CASE WHEN a.date = ? THEN 1 ELSE 0 END) as day_3,
                MAX(CASE WHEN a.date = ? THEN 1 ELSE 0 END) as day_4
            FROM riggers r
            LEFT JOIN availability a ON a.rigger_id = r.id
            WHERE r.status = 'approved'
            AND r.id IN (
                SELECT rigger_id FROM availability WHERE date =?
            )
            GROUP BY r.id
        """, (*day_strs, date_filter,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT r.id, r.name, r.phone, r.affiliation, r.city, r.token, r.last_toggled_at, r.sms_consent,
                MAX(CASE WHEN a.date = ? THEN 1 ELSE 0 END) as day_0,
                MAX(CASE WHEN a.date = ? THEN 1 ELSE 0 END) as day_1,
                MAX(CASE WHEN a.date = ? THEN 1 ELSE 0 END) as day_2,
                MAX(CASE WHEN a.date = ? THEN 1 ELSE 0 END) as day_3,
                MAX(CASE WHEN a.date = ? THEN 1 ELSE 0 END) as day_4
            FROM riggers r
            LEFT JOIN availability a ON a.rigger_id = r.id
            WHERE r.status = 'approved'
            GROUP BY r.id
        """, (*day_strs,)).fetchall()

    # Process the rows into a list of riggers with their availability
    riggers = []
    for r in rows:
        riggers.append({
            "id": r["id"],
            "name": r["name"],
            "phone": r["phone"],
            "sms_consent": r["sms_consent"],
            "availability": [r["day_0"], r["day_1"], r["day_2"], r["day_3"], r["day_4"]],
            "token": r["token"],
            "last_toggled_at_raw": r["last_toggled_at"],
            "last_toggled_at": datetime.strptime(r["last_toggled_at"],
            "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(ZoneInfo("America/Los_Angeles")).strftime("%m/%d %I:%M%p")
            if r["last_toggled_at"]
            else "Never"
        })

    if sort_by == 'last_updated':
        riggers = sorted(riggers, key=lambda r: r['last_toggled_at_raw'] or '', reverse=(sort_dir == 'desc')) # Never-updated riggers sort as the oldest possible timestamp
    else:
        riggers = sorted(riggers, key=lambda r: r['name'].split()[-1].lower(), reverse=(sort_dir == 'desc')) # Sort by last name, case-insensitive
    conn.close()
    return render_template("admin_availability.html", riggers=riggers, days=days, filter_day=filter_day, sort_by=sort_by, sort_dir=sort_dir)


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

        sms_consent = 1 if request.form.get("sms_consent") else 0

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
            "INSERT INTO riggers (name, phone, affiliation, city, token, sms_consent) VALUES (?, ?, ?, ?, ?, ?)",
            (name, phone, affiliation or None, city or None, token, sms_consent)
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

        target_date = (pacific_today() + timedelta(days=offset)).strftime("%Y-%m-%d")
        existing = conn.execute(
            "SELECT id FROM availability WHERE rigger_id = ? AND date = ?",
            (rigger["id"], target_date)
        ).fetchone()

        if existing:
            conn.execute(
                "DELETE FROM availability WHERE rigger_id = ? AND date = ?",
                (rigger["id"], target_date)
            )
        else:
            conn.execute(
                "INSERT INTO availability (rigger_id, date) VALUES (?, ?)",
                (rigger["id"], target_date)
            )

        conn.execute(
            "UPDATE riggers SET last_toggled_at = datetime('now') WHERE id = ?",
            (rigger["id"],)
        )
        conn.commit()
        conn.close()
        return redirect(url_for("availability", token=token))

    days = []
    for i in range(5):
        d = pacific_today() + timedelta(days=i)
        target_date = d.strftime("%Y-%m-%d")
        available = conn.execute(
            "SELECT id FROM availability WHERE rigger_id = ? AND date = ?",
            (rigger["id"], target_date)
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
                       error="Name and phone are required.")

        digits = ''.join(filter(str.isdigit, phone))
        if len(digits) == 10:
            phone = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        elif len(digits) == 11 and digits[0] == '1':
            phone = f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
        else:
            return render_template("edit_own_info.html", rigger=rigger,
                       error="Please enter a valid 10-digit US phone number.")

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
    return render_template("edit_own_info.html", rigger=rigger)






if __name__ == "__main__":
    app.run(debug=True)