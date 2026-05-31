from flask import Flask, render_template, request, redirect, url_for
from database import get_db

app = Flask(__name__)


@app.route("/")
def home():
    return "Community Riggers is running."


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


if __name__ == "__main__":
    app.run(debug=True)