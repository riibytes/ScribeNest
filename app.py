import os
import sqlite3
import uuid
import requests
from authlib.integrations.flask_client import OAuth
from functools import wraps
from pypdf import PdfReader
import io

def extract_text_from_pdf(file_storage_or_bytes):
    try:
        if isinstance(file_storage_or_bytes, bytes):
            reader = PdfReader(io.BytesIO(file_storage_or_bytes))
        else:
            reader = PdfReader(file_storage_or_bytes)
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return text
    except Exception:
        return ""

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    send_from_directory
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from supabase import create_client, Client

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


# =========================================================
# CONFIGURATION & SUPABASE SETUP
# =========================================================

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv(
    "SECRET_KEY",
    "dev-secret-change-this"
)

# Initialize Supabase Client Safely for Serverless
url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")
try:
    supabase: Client = create_client(url, key) if url and key else None
except Exception:
    supabase = None

# Initialize OAuth for Google Login
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# Serverless path configuration for Vercel read-only system vs local
if os.environ.get("VERCEL"):
    BASE_DIR = "/tmp"
    DATABASE = os.path.join(BASE_DIR, "database.db")
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATABASE = os.path.join(BASE_DIR, "database.db")
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")


# =========================================================
# FILE UPLOAD CONFIGURATION
# =========================================================

PDF_FOLDER = os.path.join(
    UPLOAD_FOLDER,
    "pdfs"
)

IMAGE_FOLDER = os.path.join(
    UPLOAD_FOLDER,
    "images"
)

ALLOWED_PDF_EXTENSIONS = {
    "pdf"
}

ALLOWED_IMAGE_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp"
}

ALLOWED_DOC_EXTENSIONS = {
    "doc",
    "docx",
    "ppt",
    "pptx"
}

# Maximum file size = 20 MB
app.config["MAX_CONTENT_LENGTH"] = (
    20 * 1024 * 1024
)


# =========================================================
# FULL 12-SECTION CURRICULUM STRUCTURE & SUBJECTS
# =========================================================

VIT_CURRICULUM_DATA = {
    "Programme Core": [
        ("CCA2001", "Cloud Computing and Virtualization"),
        ("CCA2002", "Cloud Architecture and Services"),
        ("CCA2006", "Cloud Automation Tools and Applications"),
        ("CCA3001", "Cloud Data Management"),
        ("CCA3002", "Fog and Edge Computing"),
        ("CCA3006", "Cloud Security Management"),
        ("CCA3007", "High Performance Computing"),
        ("CSD3009", "DATA STRUCTURES AND ANALYSIS OF ALGORITHMS"),
        ("CSE2001", "Object Oriented Programming with C++"),
        ("CSE2003", "Computer Architecture and Organization"),
        ("CSE2004", "Theory Of Computation And Compiler Design"),
        ("CSE3001", "Database Management Systems"),
        ("CSE3003", "Operating System"),
        ("CSE3006", "Computer Networks"),
        ("ECE2002", "Digital Logic Design")
    ],
    "Programme Elective": [
        ("CCA2016", "Introduction to Cloud Services"),
        ("CCA3010", "Containerization and Micro Services"),
        ("CCA3011", "Internet of Things"),
        ("CCA3012", "Parallel and Distributed Algorithms"),
        ("CCA3013", "Cloud Orchestration Services"),
        ("CCA3016", "Cloud Storage Infrastructures"),
        ("CCA3017", "Cloud Strategy Planning and Management"),
        ("CCA4001", "Application Development using Microservices and Serverless Computing"),
        ("CCA4002", "Sensor-Cloud for Internet of Things"),
        ("CCA4003", "Container Orchestration and Infrastructure Automation"),
        ("CCA4004", "Cloud Performance Tuning"),
        ("CCA4005", "Cloud Application Development"),
        ("CSE3007", "Artificial Intelligence"),
        ("CSE3015", "AWS Cloud Practitioner"),
        ("CSE3016", "AWS Solution Architect"),
        ("CSE3017", "Salesforce"),
        ("CSE4003", "Bigdata Analytics")
    ],
    "University Core - Natural Science Core": [
        ("CHY1005", "Introduction to Computational chemistry"),
        ("MAT1003", "Calculus"),
        ("MAT2002", "Discrete Mathematics and Graph Theory"),
        ("MAT3002", "Applied Linear Algebra"),
        ("MAT3003", "Probability, Statistics and Reliability"),
        ("PHY1003", "Introduction to Computational Physics")
    ],
    "University Core - Basic Engineering Sciences Core": [
        ("CSA2001", "Fundamentals in AI and ML"),
        ("EEE1001", "Electric Circuits and Systems"),
        ("MEE2014", "Engineering Design and Modelling")
    ],
    "University Core - Skill Development Courses": [
        ("CSE1021", "Introduction to Problem Solving and Programming"),
        ("CSE2006", "Programming in Java"),
        ("PLA1004", "Competitive Coding Practices"),
        ("PLA1006", "Lateral Thinking"),
        ("SST1003", "Professional Communication Skills for Engineers"),
        ("SST2003", "Dynamics of workplace communication Skills")
    ],
    "University Core - Humanities Social Science and Management Core": [
        ("CHY1006", "Environmental Sustainability"),
        ("ENG1004", "EFFECTIVE TECHNICAL COMMUNICATION"),
        ("ENG2005", "Advanced Technical Communication")
    ],
    "University Core - Project and Internships": [
        ("DSN2092", "SUMMER INDUSTRIAL INTERNSHIP"),
        ("DSN2093", "SEMESTER INTERNSHIP"),
        ("DSN2098", "Project Exhibition - I"),
        ("DSN2099", "Project Exhibition - II"),
        ("DSN3099", "Engineering Project in Community Service"),
        ("DSN4091", "Capstone Project - Phase 1"),
        ("DSN4092", "Capstone Project - Phase 2")
    ],
    "University Elective - Natural Science Electives": [
        ("CHY2007", "Modelling and Simulation of Biological Systems"),
        ("MAT2003", "Applied Numerical Method"),
        ("MAT2004", "Operations Research"),
        ("MAT2005", "Transform Techniques and Difference Equations"),
        ("MAT3004", "Random Process"),
        ("MAT3008", "Computational Game Theory"),
        ("PHY2011", "Biophysics")
    ],
    "University Elective - Multidisciplinary Electives": [
        ("BIO1501", "Bio Inspired Design"),
        ("CDS3005", "Foundations of Data Science"),
        ("CSG2003", "Human Computer Interaction"),
        ("EAC4012", "Body Area Networks"),
        ("ECE4006", "Sensors And Iot"),
        ("ENG3001", "Introduction to Computational Linguistics"),
        ("MEA3015", "UNMANNED AERIAL VEHICLES")
    ],
    "University Elective - Humanities, Social Sciences and Management Electives": [
        ("BMT1013", "Human Resource Management"),
        ("BMT2017", "International Business"),
        ("HUM1002", "Emotional Intelligence"),
        ("HUM2001", "Behavioural Science"),
        ("MGT1002", "PRINCIPLES OF MANAGEMENT AND ORGANIZATIONAL BEHAVIOUR"),
        ("MGT2003", "Technology Entrepreneurship")
    ],
    "University Elective - Open Electives": [
        ("CSD1001", "Principles Of Digital Forensics"),
        ("CSD3010", "Cyber Physical Systems"),
        ("CSD4002", "Ethical Hacking"),
        ("ONL1010", "Applied Machine Learning in Python"),
        ("ONL1021", "HTML, CSS and JavaScript for Web Developers"),
        ("ONL1022", "Industrial IoT Markets and Security"),
        ("ONL1023", "Introduction to Self-Driving Cars"),
        ("ONL1028", "The Bits and Bytes of Computer Networking"),
        ("ONL1032", "IBM AI Engineering Professional Certificate")
    ],
    "Non - Graded Mandatory Courses": [
        ("CSE0001", "Digital Literacy"),
        ("CSE0002", "OPEN SOURCE SOFTWARE (LINUX ADMINISTRATION)"),
        ("EXC0001", "EXTRA CURRICULAR ACTIVITIES"),
        ("HUM0002", "Swachh Bharat"),
        ("HUM0003", "INDIAN CONSTITUTION"),
        ("HUM0004", "INDIAN HERITAGE"),
        ("UHV0001", "Universal Human Values - I"),
        ("UHV0002", "Universal Human Values - II")
    ]
}


# =========================================================
# DATABASE
# =========================================================

def get_db():
    connection = sqlite3.connect(
        DATABASE
    )
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    try:
        db = get_db()

        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                subject TEXT NOT NULL,
                program TEXT DEFAULT '',
                content TEXT NOT NULL,
                tags TEXT DEFAULT '',
                is_public INTEGER DEFAULT 0,
                is_favorite INTEGER DEFAULT 0,
                file_name TEXT DEFAULT '',
                file_path TEXT DEFAULT '',
                file_type TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
            )
        """)

        db.commit()
        db.close()

        os.makedirs(PDF_FOLDER, exist_ok=True)
        os.makedirs(IMAGE_FOLDER, exist_ok=True)
    except Exception as e:
        print(f"Database init handled: {e}")


# =========================================================
# LOGIN DECORATOR
# =========================================================

def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash(
                "Please login first.",
                "error"
            )
            return redirect(
                url_for(
                    "login",
                    next=request.path if request.method == "GET" else None
                )
            )
        return function(
            *args,
            **kwargs
        )
    return wrapper


def get_safe_next():
    """Return the saved post-login page, only if it is a local path."""
    target = session.pop("next_url", "") or ""
    if target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return None


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():
    return render_template(
        "index.html"
    )


# =========================================================
# SUBJECTS CURRICULUM & LOGIN GUARD
# =========================================================

@app.route("/subjects")
def public_subjects():
    return render_template("subjects.html", curriculum=VIT_CURRICULUM_DATA)


@app.route("/subjects/<code>")
def subject_detail(code):
    if "user_id" not in session:
        flash("Please login first to view notes and materials for this subject.", "error")
        return redirect(url_for("login", next=request.path))
    
    db = get_db()
    notes = db.execute(
        "SELECT notes.*, users.name AS author FROM notes JOIN users ON notes.user_id = users.id WHERE notes.subject LIKE ? OR notes.content LIKE ? ORDER BY notes.updated_at DESC",
        (f"%{code}%", f"%{code}%")
    ).fetchall()
    db.close()
    return render_template("subject_notes.html", code=code, notes=notes)


# =========================================================
# GOOGLE OAUTH LOGIN
# =========================================================

@app.route("/login/google")
def google_login():
    redirect_uri = url_for("google_authorized", _external=True)
    return google.authorize_redirect(redirect_uri)


@app.route("/login/google/authorized")
def google_authorized():
    try:
        token = google.authorize_access_token()
        resp = google.get("https://www.googleapis.com/oauth2/v3/userinfo")
        user_info = resp.json()
    except Exception as e:
        flash("Google authentication failed.", "error")
        return redirect(url_for("login"))

    email = user_info.get("email", "").lower()
    name = user_info.get("name", "Student")

    allowed_domains = ("@gmail.com", "@vitbhopal.ac.in")
    if not email.endswith(allowed_domains):
        flash("Only authorized Gmail or VIT Bhopal accounts are allowed.", "error")
        return redirect(url_for("login"))

    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE email = ?",
        (email,)
    ).fetchone()

    if not user:
        dummy_password = generate_password_hash(str(uuid.uuid4()))
        db.execute(
            """
            INSERT INTO users (name, email, password)
            VALUES (?, ?, ?)
            """,
            (name, email, dummy_password)
        )
        db.commit()
        user = db.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

    db.close()

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]

    flash("Welcome back to ScribeNest!", "success")
    return redirect(get_safe_next() or url_for("dashboard"))


# =========================================================
# REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = (
            request.form["email"]
            .strip()
            .lower()
        )
        password = request.form["password"]

        if not name or not email or not password:
            flash(
                "All fields are required.",
                "error"
            )
            return redirect(
                url_for("register")
            )

        allowed_domains = ("@gmail.com", "@vitbhopal.ac.in")
        if not email.endswith(allowed_domains):
            flash(
                "Please register using an authorized Gmail or VIT Bhopal email address.",
                "error"
            )
            return redirect(
                url_for("register")
            )

        if len(password) < 6:
            flash(
                "Password must contain at least 6 characters.",
                "error"
            )
            return redirect(
                url_for("register")
            )

        db = get_db()
        existing_user = db.execute(
            """
            SELECT id
            FROM users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

        if existing_user:
            db.close()
            flash(
                "An account with this email already exists.",
                "error"
            )
            return redirect(
                url_for("login")
            )

        hashed_password = (
            generate_password_hash(password)
        )

        db.execute(
            """
            INSERT INTO users
            (
                name,
                email,
                password
            )
            VALUES (?, ?, ?)
            """,
            (
                name,
                email,
                hashed_password
            )
        )
        db.commit()
        db.close()

        flash(
            "Account created successfully. Please login.",
            "success"
        )
        return redirect(
            url_for("login")
        )

    return render_template(
        "register.html"
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():
    if request.method == "GET":
        if request.args.get("next"):
            session["next_url"] = request.args["next"]
        else:
            session.pop("next_url", None)

    if request.method == "POST":
        email = (
            request.form["email"]
            .strip()
            .lower()
        )
        password = request.form["password"]

        db = get_db()
        user = db.execute(
            """
            SELECT *
            FROM users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()
        db.close()

        if user and check_password_hash(
            user["password"],
            password
        ):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            flash(
                "Welcome back to ScribeNest!",
                "success"
            )
            return redirect(
                get_safe_next() or url_for("dashboard")
            )

        flash(
            "Invalid email or password.",
            "error"
        )

    return render_template(
        "login.html"
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():
    session.clear()
    flash(
        "You have been logged out.",
        "success"
    )
    return redirect(
        url_for("home")
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    notes = db.execute(
        """
        SELECT *
        FROM notes
        WHERE user_id = ?
        ORDER BY updated_at DESC
        """,
        (
            session["user_id"],
        )
    ).fetchall()

    total_notes = len(notes)

    favorite_count = db.execute(
        """
        SELECT COUNT(*)
        FROM notes
        WHERE user_id = ?
        AND is_favorite = 1
        """,
        (
            session["user_id"],
        )
    ).fetchone()[0]

    public_count = db.execute(
        """
        SELECT COUNT(*)
        FROM notes
        WHERE user_id = ?
        AND is_public = 1
        """,
        (
            session["user_id"],
        )
    ).fetchone()[0]

    db.close()

    return render_template(
        "dashboard.html",
        notes=notes,
        total_notes=total_notes,
        favorite_count=favorite_count,
        public_count=public_count
    )


# =========================================================
# CREATE TEXT NOTE
# =========================================================

@app.route(
    "/notes/create",
    methods=["GET", "POST"]
)
@login_required
def create_note():
    if request.method == "POST":
        title = (
            request.form["title"]
            .strip()
        )
        subject = (
            request.form["subject"]
            .strip()
        )
        program = (
            request.form.get("program", "")
            .strip()
        )
        content = (
            request.form["content"]
            .strip()
        )
        tags = (
            request.form.get(
                "tags",
                ""
            )
            .strip()
        )
        is_public = (
            1
            if request.form.get("is_public")
            else 0
        )

        if not title or not subject or not content:
            flash(
                "Title, subject and content are required.",
                "error"
            )
            return redirect(
                url_for("create_note")
            )

        db = get_db()
        db.execute(
            """
            INSERT INTO notes
            (
                user_id,
                title,
                subject,
                program,
                content,
                tags,
                is_public
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                title,
                subject,
                program,
                content,
                tags,
                is_public
            )
        )
        db.commit()
        db.close()

        flash(
            "Note created successfully!",
            "success"
        )
        return redirect(
            url_for("dashboard")
        )

    return render_template(
        "create_note.html",
        programs=VIT_CURRICULUM_DATA
    )


# =========================================================
# UPLOAD PDF / IMAGE (SUPABASE CLOUD STORAGE INTEGRATED)
# =========================================================

@app.route(
    "/notes/upload",
    methods=["GET", "POST"]
)
@login_required
def upload_note():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        subject = request.form.get("subject", "").strip()
        tags = request.form.get("tags", "").strip()
        content = request.form.get("content", "").strip()
        is_public = 1 if request.form.get("is_public") else 0
        uploaded_file = request.files.get("file")

        if not title or not subject:
            flash("Title and subject are required.", "error")
            return redirect(url_for("upload_note"))

        if not uploaded_file or not uploaded_file.filename:
            flash("Please select a file.", "error")
            return redirect(url_for("upload_note"))

        original_filename = uploaded_file.filename

        if "." not in original_filename:
            flash("Invalid file.", "error")
            return redirect(url_for("upload_note"))

        extension = original_filename.rsplit(".", 1)[1].lower()

        if extension in ALLOWED_PDF_EXTENSIONS:
            file_type = "pdf"
        elif extension in ALLOWED_IMAGE_EXTENSIONS:
            file_type = "image"
        elif extension in ALLOWED_DOC_EXTENSIONS:
            file_type = "document"
        else:
            flash("Only PDF, Images, Word, and PowerPoint files are allowed.", "error")
            return redirect(url_for("upload_note"))

        safe_filename = secure_filename(original_filename)
        if not safe_filename:
            flash("Invalid filename.", "error")
            return redirect(url_for("upload_note"))

        extension_with_dot = os.path.splitext(safe_filename)[1]
        unique_filename = str(uuid.uuid4()) + extension_with_dot
        storage_path = f"uploads/{unique_filename}"

        if supabase is None:
            flash("Supabase storage is not configured.", "error")
            return redirect(url_for("upload_note"))

        try:
            file_bytes = uploaded_file.read()
            supabase.storage.from_("notes-bucket").upload(
                path=storage_path,
                file=file_bytes,
                file_options={"content-type": uploaded_file.content_type}
            )
            public_url_response = supabase.storage.from_("notes-bucket").get_public_url(storage_path)
            database_file_path = public_url_response if isinstance(public_url_response, str) else public_url_response.get("publicUrl", storage_path)
        except Exception as e:
            flash(f"Cloud upload failed: {str(e)}", "error")
            return redirect(url_for("upload_note"))

        db = get_db()
        db.execute(
            """
            INSERT INTO notes
            (
                user_id,
                title,
                subject,
                program,
                content,
                tags,
                is_public,
                file_name,
                file_path,
                file_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                title,
                subject,
                subject.split(" - ")[0],
                content,
                tags,
                is_public,
                safe_filename,
                database_file_path,
                file_type
            )
        )
        db.commit()
        db.close()

        flash("Your note has been uploaded successfully to Supabase cloud storage!", "success")
        return redirect(url_for("dashboard"))

    return render_template(
        "upload_note.html",
        programs=VIT_CURRICULUM_DATA
    )


# =========================================================
# VIEW NOTE
# =========================================================

@app.route(
    "/notes/<int:note_id>"
)
@login_required
def view_note(note_id):
    db = get_db()
    note = db.execute(
        """
        SELECT
            notes.*,
            users.name AS author
        FROM notes
        JOIN users
        ON notes.user_id = users.id
        WHERE notes.id = ?
        """,
        (
            note_id,
        )
    ).fetchone()
    db.close()

    if not note:
        flash(
            "Note not found.",
            "error"
        )
        return redirect(
            url_for("dashboard")
        )

    if (
        note["user_id"] != session["user_id"]
        and not note["is_public"]
    ):
        flash(
            "This note is private.",
            "error"
        )
        return redirect(
            url_for("dashboard")
        )

    return render_template(
        "note.html",
        note=note
    )


# =========================================================
# EDIT NOTE
# =========================================================

@app.route(
    "/notes/<int:note_id>/edit",
    methods=["GET", "POST"]
)
@login_required
def edit_note(note_id):
    db = get_db()
    note = db.execute(
        """
        SELECT *
        FROM notes
        WHERE id = ?
        AND user_id = ?
        """,
        (
            note_id,
            session["user_id"]
        )
    ).fetchone()

    if not note:
        db.close()
        flash(
            "Note not found.",
            "error"
        )
        return redirect(
            url_for("dashboard")
        )

    if request.method == "POST":
        title = (
            request.form["title"]
            .strip()
        )
        subject = (
            request.form["subject"]
            .strip()
        )
        program = (
            request.form.get("program", "")
            .strip()
        )
        content = (
            request.form["content"]
            .strip()
        )
        tags = (
            request.form.get(
                "tags",
                ""
            )
            .strip()
        )
        is_public = (
            1
            if request.form.get("is_public")
            else 0
        )

        db.execute(
            """
            UPDATE notes
            SET
                title = ?,
                subject = ?,
                program = ?,
                content = ?,
                tags = ?,
                is_public = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            AND user_id = ?
            """,
            (
                title,
                subject,
                program,
                content,
                tags,
                is_public,
                note_id,
                session["user_id"]
            )
        )
        db.commit()
        db.close()

        flash(
            "Note updated successfully!",
            "success"
        )
        return redirect(
            url_for(
                "view_note",
                note_id=note_id
            )
        )

    db.close()

    return render_template(
        "edit_note.html",
        note=note,
        programs=VIT_CURRICULUM_DATA
    )


# =========================================================
# DELETE NOTE
# =========================================================

@app.route(
    "/notes/<int:note_id>/delete",
    methods=["POST"]
)
@login_required
def delete_note(note_id):
    db = get_db()
    db.execute(
        """
        DELETE FROM notes
        WHERE id = ?
        AND user_id = ?
        """,
        (
            note_id,
            session["user_id"]
        )
    )
    db.commit()
    db.close()

    flash(
        "Note deleted.",
        "success"
    )
    return redirect(
        url_for("dashboard")
    )


# =========================================================
# FAVORITE NOTE
# =========================================================

@app.route(
    "/notes/<int:note_id>/favorite",
    methods=["POST"]
)
@login_required
def favorite_note(note_id):
    db = get_db()
    note = db.execute(
        """
        SELECT is_favorite
        FROM notes
        WHERE id = ?
        AND user_id = ?
        """,
        (
            note_id,
            session["user_id"]
        )
    ).fetchone()

    if note:
        new_value = (
            0
            if note["is_favorite"]
            else 1
        )
        db.execute(
            """
            UPDATE notes
            SET is_favorite = ?
            WHERE id = ?
            AND user_id = ?
            """,
            (
                new_value,
                note_id,
                session["user_id"]
            )
        )
        db.commit()

    db.close()

    return redirect(
        request.referrer
        or
        url_for("dashboard")
    )


# =========================================================
# SMART SEARCH (MATCHING COURSE CODES & TITLES)
# =========================================================

@app.route("/search")
@login_required
def search():
    query = (
        request.args.get(
            "q",
            ""
        )
        .strip()
    )

    db = get_db()
    notes = db.execute(
        """
        SELECT
            notes.*,
            users.name AS author
        FROM notes
        JOIN users
        ON notes.user_id = users.id
        WHERE
            (
                notes.user_id = ?
                OR notes.is_public = 1
            )
            AND
            (
                notes.title LIKE ?
                OR notes.subject LIKE ?
                OR notes.program LIKE ?
                OR notes.content LIKE ?
                OR notes.tags LIKE ?
            )
        ORDER BY notes.updated_at DESC
        """,
        (
            session["user_id"],
            f"%{query}%",
            f"%{query}%",
            f"%{query}%",
            f"%{query}%",
            f"%{query}%"
        )
    ).fetchall()
    db.close()

    return render_template(
        "public_notes.html",
        notes=notes,
        query=query,
        programs=VIT_CURRICULUM_DATA
    )


# =========================================================
# PUBLIC VAULT
# =========================================================

@app.route("/vault")
@login_required
def vault():
    selected_program = request.args.get("program", "").strip()
    selected_subject = request.args.get("subject", "").strip()

    db = get_db()
    
    query = """
        SELECT
            notes.*,
            users.name AS author
        FROM notes
        JOIN users
        ON notes.user_id = users.id
        WHERE notes.is_public = 1
    """
    params = []

    if selected_program:
        query += " AND notes.program = ?"
        params.append(selected_program)

    if selected_subject:
        query += " AND notes.subject = ?"
        params.append(selected_subject)

    query += " ORDER BY notes.created_at DESC"

    notes = db.execute(query, params).fetchall()
    db.close()

    return render_template(
        "public_notes.html",
        notes=notes,
        query="",
        programs=VIT_CURRICULUM_DATA,
        selected_program=selected_program,
        selected_subject=selected_subject
    )


# =========================================================
# AI TOOLS (WITH SUPABASE PDF FILE EXTRACTION SUPPORT)
# =========================================================

def get_ai_client():
    api_key = os.getenv(
        "OPENAI_API_KEY"
    )
    if not api_key or OpenAI is None:
        return None
    return OpenAI(
        api_key=api_key
    )


def ask_ai(prompt):
    client = get_ai_client()
    if client is None:
        return (
            "AI is not configured yet. "
            "Add your OPENAI_API_KEY to your environment variables."
        )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are ScribeNest AI, a helpful study assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as error:
        return (
            "AI request failed: "
            + str(error)
        )


@app.route(
    "/ai",
    methods=["GET", "POST"]
)
@login_required
def ai_tools():
    result = None

    if request.method == "POST":
        content = request.form.get("content", "").strip()
        action = request.form.get("action")
        note_id = request.form.get("note_id")

        if note_id:
            db = get_db()
            note = db.execute("SELECT * FROM notes WHERE id = ? AND (user_id = ? OR is_public = 1)", (note_id, session["user_id"])).fetchone()
            db.close()
            if note:
                if note["file_type"] == "pdf" and note["file_path"]:
                    try:
                        res = requests.get(note["file_path"])
                        if res.status_code == 200:
                            pdf_extracted = extract_text_from_pdf(res.content)
                            content = pdf_extracted + "\n" + note["content"]
                    except Exception:
                        content = note["content"]
                else:
                    content = note["content"]

        if not content:
            flash(
                "Please enter study material or select a note with content.",
                "error"
            )
            return redirect(
                url_for("ai_tools")
            )

        if action == "summary":
            prompt = f"""
You are ScribeNest AI.
Summarize the following student study material.
Give:
1. Short summary
2. Important concepts
3. Key points
4. Exam-focused points

Study material:
{content}
"""
        elif action == "questions":
            prompt = f"""
You are ScribeNest AI.
Generate 10 useful exam and viva questions
from the following study material.
Include a mixture of:
- Short answer questions
- Conceptual questions
- Difference questions
- Application questions

Study material:
{content}
"""
        elif action == "flashcards":
            prompt = f"""
You are ScribeNest AI.
Create 10 study flashcards from the
following material.
Format:
Q:
A:

Study material:
{content}
"""
        elif action == "ask":
            question = (
                request.form.get(
                    "question",
                    ""
                )
                .strip()
            )
            prompt = f"""
You are ScribeNest AI.
Answer the student's question using
ONLY the provided study material as
the main source.

Study material:
{content}

Student question:
{question}
"""
        else:
            prompt = content

        result = ask_ai(
            prompt
        )

    db = get_db()
    user_notes = db.execute("SELECT id, title, subject FROM notes WHERE user_id = ? ORDER BY updated_at DESC", (session["user_id"],)).fetchall()
    db.close()

    return render_template(
        "ai.html",
        result=result,
        notes=user_notes
    )


# =========================================================
# FILE TOO LARGE ERROR HANDLER
# =========================================================

@app.errorhandler(413)
def file_too_large(error):
    flash(
        "File is too large. Maximum size is 20 MB.",
        "error"
    )
    return redirect(
        url_for("upload_note")
    )


# =========================================================
# START APPLICATION & PRODUCTION HOOK
# =========================================================

init_db()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5500)