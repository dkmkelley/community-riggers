from flask import Flask, render_template, request, redirect, url_for
from database import get_db

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

        conn = get_db()
        conn.execute(
            "INSERT INTO riggers (name, phone, affiliation, city) VALUES (?, ?, ?, ?)",
            (name, phone, affiliation or None, city or None)
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

if __name__ == "__main__":
    app.run(debug=True)