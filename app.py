from flask import Flask, render_template, request, redirect, url_for
from database import get_db, generate_token
from datetime import date, timedelta

app = Flask(__name__)


@app.route("/")
def home():
    return redirect(url_for("list_riggers"))


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

@app.route("/riggers")
def list_riggers():
    conn = get_db()
    riggers = conn.execute("SELECT id, name, phone, affiliation, city FROM riggers ORDER BY name").fetchall()
    conn.close()
    return render_template("riggers.html", riggers=riggers)

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
        day = request.form.get("day")

        if day == "today":
            existing = conn.execute(
                "SELECT id FROM availability WHERE rigger_id = ? AND date = date('now')",
                (rigger["id"],)
            ).fetchone()
            if existing:
                conn.execute(
                    "DELETE FROM availability WHERE rigger_id = ? AND date = date('now')",
                    (rigger["id"],)
                )
            else:
                conn.execute(
                    "INSERT INTO availability (rigger_id, date) VALUES (?, date('now'))",
                    (rigger["id"],)
                )

        elif day == "tomorrow":
            existing = conn.execute(
                "SELECT id FROM availability WHERE rigger_id = ? AND date = date('now', '+1 day')",
                (rigger["id"],)
            ).fetchone()
            if existing:
                conn.execute(
                    "DELETE FROM availability WHERE rigger_id = ? AND date = date('now', '+1 day')",
                    (rigger["id"],)
                )
            else:
                conn.execute(
                    "INSERT INTO availability (rigger_id, date) VALUES (?, date('now', '+1 day'))",
                    (rigger["id"],)
                )
        else:
            conn.close()
            return "Invalid request.", 400

        conn.commit()
        conn.close()
        return redirect(url_for("availability", token=token))

    available_today = conn.execute(
        "SELECT id FROM availability WHERE rigger_id = ? AND date = date('now')",
        (rigger["id"],)
    ).fetchone() is not None

    available_tomorrow = conn.execute(
        "SELECT id FROM availability WHERE rigger_id = ? AND date = date('now', '+1 day')",
        (rigger["id"],)
    ).fetchone() is not None

    today_str = date.today().strftime("%B %d, %Y")
    tomorrow_str = (date.today() + timedelta(days=1)).strftime("%B %d, %Y")

    conn.close()
    return render_template("availability.html",
                           rigger=rigger,
                           available_today=available_today,
                           available_tomorrow=available_tomorrow,
                           today_str=today_str,
                           tomorrow_str=tomorrow_str)


if __name__ == "__main__":
    app.run(debug=True)