from flask import Flask, render_template, request, redirect, url_for
from database import get_db, generate_token
from datetime import date, timedelta

app = Flask(__name__)

# Default route. Redirects to the list of riggers
@app.route("/")
def home():
    return redirect(url_for("list_riggers"))

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
        
        token = generate_token()

        conn = get_db()
        conn.execute(
            "INSERT INTO riggers (name, phone, affiliation, city, token) VALUES (?, ?, ?, ?, ?)",
            (name, phone, affiliation or None, city or None, token)
        )
        conn.commit()
        conn.close()

        return redirect(url_for("home"))

    return render_template("add_rigger.html")


# Route to list all riggers
@app.route("/riggers")
def list_riggers():
    conn = get_db()
    riggers = conn.execute("SELECT id, name, phone, affiliation, city, token FROM riggers ORDER BY name").fetchall()
    conn.close()
    return render_template("riggers.html", riggers=riggers)

# Route to edit a rigger's information
@app.route("/riggers/<int:id>/edit", methods=["GET", "POST"])
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
def admin_availability():
    conn = get_db()

    days = []
    for i in range(5):
        d = date.today() + timedelta(days=i)
        if i == 0:
            label = "Today"
        elif i == 1:
            label = "Tomorrow"
        else:
            label = d.strftime("%A")
        days.append({
            "label": label,
            "date_str": d.strftime("%b %d")
        })

    rows = conn.execute("""
        SELECT r.id, r.name, r.phone, r.affiliation, r.city,
               MAX(CASE WHEN a.date = date('now') THEN 1 ELSE 0 END) as day_0,
               MAX(CASE WHEN a.date = date('now', '+1 days') THEN 1 ELSE 0 END) as day_1,
               MAX(CASE WHEN a.date = date('now', '+2 days') THEN 1 ELSE 0 END) as day_2,
               MAX(CASE WHEN a.date = date('now', '+3 days') THEN 1 ELSE 0 END) as day_3,
               MAX(CASE WHEN a.date = date('now', '+4 days') THEN 1 ELSE 0 END) as day_4
        FROM riggers r
        LEFT JOIN availability a ON a.rigger_id = r.id
        GROUP BY r.id
        ORDER BY r.name
    """).fetchall()

    riggers = []
    for r in rows:
        riggers.append({
            "id": r["id"],
            "name": r["name"],
            "phone": r["phone"],
            "affiliation": r["affiliation"] or "—",
            "city": r["city"] or "—",
            "availability": [r["day_0"], r["day_1"], r["day_2"], r["day_3"], r["day_4"]]
        })

    conn.close()
    return render_template("admin_availability.html", riggers=riggers, days=days)

# Route for riggers to set their availability for the next 5 days using a unique token link.
@app.route("/availability/<token>", methods=["GET", "POST"])
def availability(token):
    conn = get_db()
    rigger = conn.execute(
        "SELECT * FROM riggers WHERE token = ?", (token,)
    ).fetchone()

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


if __name__ == "__main__":
    app.run(debug=True)