import os
import uuid
import requests
import io
import psycopg2
import psycopg2.extras
from authlib.integrations.flask_client import OAuth
from datetime import timedelta
from functools import wraps
from pypdf import PdfReader

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
app.config.update(
    PERMANENT_SESSION_LIFETIME=timedelta(days=365),
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=bool(os.environ.get("VERCEL")),
)
app.secret_key = os.getenv(
    "SECRET_KEY",
    "dev-secret-change-this"
)

# Initialize Supabase Client Safely for Serverless
url = (os.getenv("SUPABASE_URL") or "").strip().strip('"').strip("'")
key = (os.getenv("SUPABASE_KEY") or "").strip().strip('"').strip("'")
supabase = None
SUPABASE_ERROR = ""
if not url or not key:
    missing = [n for n, v in (("SUPABASE_URL", url), ("SUPABASE_KEY", key)) if not v]
    SUPABASE_ERROR = "Missing environment variable(s): " + ", ".join(missing)
else:
    try:
        supabase = create_client(url, key)
    except Exception as e:
        SUPABASE_ERROR = f"{type(e).__name__}: {e}"
if SUPABASE_ERROR:
    print("Supabase NOT configured -", SUPABASE_ERROR)

# Initialize OAuth for Google Login
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)


# =========================================================
# FILE UPLOAD CONFIGURATION
# =========================================================

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
    "Programme Core": {
        "Cloud Computing": [
            ("CCA2001", "Cloud Computing and Virtualization"),
            ("CCA2002", "Cloud Architecture and Services"),
            ("CCA2006", "Cloud Automation Tools and Applications"),
            ("CCA3001", "Cloud Data Management"),
            ("CCA3002", "Fog and Edge Computing"),
            ("CCA3006", "Cloud Security Management"),
            ("CCA3007", "High Performance Computing")
        ],
        "Computer Science": [
            ("CSD3009", "DATA STRUCTURES AND ANALYSIS OF ALGORITHMS"),
            ("CSE2001", "Object Oriented Programming with C++"),
            ("CSE2003", "Computer Architecture and Organization"),
            ("CSE2004", "Theory Of Computation And Compiler Design"),
            ("CSE3001", "Database Management Systems"),
            ("CSE3003", "Operating System"),
            ("CSE3006", "Computer Networks")
        ],
        "Electronics": [
            ("ECE2002", "Digital Logic Design")
        ]
    },
    "Programme Elective": {
        "Cloud & Infrastructure": [
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
            ("CCA4005", "Cloud Application Development")
        ],
        "Advanced Computing": [
            ("CSE3007", "Artificial Intelligence"),
            ("CSE3015", "AWS Cloud Practitioner"),
            ("CSE3016", "AWS Solution Architect"),
            ("CSE3017", "Salesforce"),
            ("CSE4003", "Bigdata Analytics")
        ]
    },
    "University Core - Natural Science Core": {
        "Sciences & Math": [
            ("CHY1005", "Introduction to Computational chemistry"),
            ("MAT1003", "Calculus"),
            ("MAT2002", "Discrete Mathematics and Graph Theory"),
            ("MAT3002", "Applied Linear Algebra"),
            ("MAT3003", "Probability, Statistics and Reliability"),
            ("PHY1003", "Introduction to Computational Physics")
        ]
    },
    "University Core - Basic Engineering Sciences Core": {
        "Engineering": [
            ("CSA2001", "Fundamentals in AI and ML"),
            ("EEE1001", "Electric Circuits and Systems"),
            ("MEE2014", "Engineering Design and Modelling")
        ]
    },
    "University Core - Skill Development Courses": {
        "Skills": [
            ("CSE1021", "Introduction to Problem Solving and Programming"),
            ("CSE2006", "Programming in Java"),
            ("PLA1004", "Competitive Coding Practices"),
            ("PLA1006", "Lateral Thinking"),
            ("SST1003", "Professional Communication Skills for Engineers"),
            ("SST2003", "Dynamics of workplace communication Skills")
        ]
    },
    "University Core - Humanities Social Science and Management Core": {
        "Humanities": [
            ("CHY1006", "Environmental Sustainability"),
            ("ENG1004", "EFFECTIVE TECHNICAL COMMUNICATION"),
            ("ENG2005", "Advanced Technical Communication")
        ]
    },
    "University Core - Project and Internships": {
        "Projects": [
            ("DSN2092", "SUMMER INDUSTRIAL INTERNSHIP"),
            ("DSN2093", "SEMESTER INTERNSHIP"),
            ("DSN2098", "Project Exhibition - I"),
            ("DSN2099", "Project Exhibition - II"),
            ("DSN3099", "Engineering Project in Community Service"),
            ("DSN4091", "Capstone Project - Phase 1"),
            ("DSN4092", "Capstone Project - Phase 2")
        ]
    },
    "University Elective - Natural Science Electives": {
        "Electives": [
            ("CHY2007", "Modelling and Simulation of Biological Systems"),
            ("MAT2003", "Applied Numerical Method"),
            ("MAT2004", "Operations Research"),
            ("MAT2005", "Transform Techniques and Difference Equations"),
            ("MAT3004", "Random Process"),
            ("MAT3008", "Computational Game Theory"),
            ("PHY2011", "Biophysics")
        ]
    },
    "University Elective - Multidisciplinary Electives": {
        "Multidisciplinary": [
            ("BIO1501", "Bio Inspired Design"),
            ("CDS3005", "Foundations of Data Science"),
            ("CSG2003", "Human Computer Interaction"),
            ("EAC4012", "Body Area Networks"),
            ("ECE4006", "Sensors And Iot"),
            ("ENG3001", "Introduction to Computational Linguistics"),
            ("MEA3015", "UNMANNED AERIAL VEHICLES")
        ]
    },
    "University Elective - Humanities, Social Sciences and Management Electives": {
        "Management": [
            ("BMT1013", "Human Resource Management"),
            ("BMT2017", "International Business"),
            ("HUM1002", "Emotional Intelligence"),
            ("HUM2001", "Behavioural Science"),
            ("MGT1002", "PRINCIPLES OF MANAGEMENT AND ORGANIZATIONAL BEHAVIOUR"),
            ("MGT2003", "Technology Entrepreneurship")
        ]
    },
    "University Elective - Open Electives": {
        "Open": [
            ("CSD1001", "Principles Of Digital Forensics"),
            ("CSD3010", "Cyber Physical Systems"),
            ("CSD4002", "Ethical Hacking"),
            ("ONL1010", "Applied Machine Learning in Python"),
            ("ONL1021", "HTML, CSS and JavaScript for Web Developers"),
            ("ONL1022", "Industrial IoT Markets and Security"),
            ("ONL1023", "Introduction to Self-Driving Cars"),
            ("ONL1028", "The Bits and Bytes of Computer Networking"),
            ("ONL1032", "IBM AI Engineering Professional Certificate")
        ]
    },
    "Non - Graded Mandatory Courses": {
        "Mandatory": [
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
}


# =========================================================
# PROGRAMMES  ->  CURRICULUM TYPES  ->  SUBJECTS
# =========================================================

PROGRAMMES = {
    "B.Tech Programmes (4 Years)": [
        "B.Tech Aerospace Engineering",
        "B.Tech Bioengineering",
        "B.Tech Computer Science & Engineering",
        "B.Tech Computer Science & Engineering (Artificial Intelligence & Machine Learning)",
        "B.Tech Computer Science & Engineering (Cyber Security & Digital Forensics)",
        "B.Tech Computer Science & Engineering (Cloud Computing & Automation)",
        "B.Tech Computer Science & Engineering (E-Commerce Technology)",
        "B.Tech Computer Science & Engineering (Education Technology)",
        "B.Tech Computer Science & Engineering (Gaming Technology)",
        "B.Tech Computer Science & Engineering (Health Informatics)",
        "B.Tech Electronics & Communication Engineering",
        "B.Tech Electronics & Communication Engineering (Artificial Intelligence & Cybernetics)",
        "B.Tech Mechanical Engineering",
        "B.Tech Mechanical Engineering (Artificial Intelligence & Robotics)",
    ],
    "Architecture Programmes (5 Years)": ["B.Arch"],
    "Other UG Programmes (3 Years)": ["BBA (Bachelor of Business Administration)"],
    "Integrated PG Programmes (5 Years)": [
        "M.Tech Artificial Intelligence",
        "M.Tech Computer Science & Engineering (Cyber Security)",
        "M.Tech Computer Science & Engineering (Computational and Data Science)",
        "Integrated M.Tech. AI and Bioinformatics",
    ],
    "PG Programmes (2 Years)": [
        "M.Tech Computer Science & Engineering (Cyber Security & Digital Forensics)",
        "M.Tech Artificial Intelligence & Data Science",
        "M.Tech VLSI Design",
        "MBA (Master of Business Administration)",
        "MCA (Master of Computer Applications)",
    ],
    "Ph.D Programmes": [
        "Ph.D Engineering",
        "Ph.D Sciences",
        "Ph.D Business Studies",
        "Ph.D Humanities",
    ],
}

PROGRAMME_CURRICULA = {
    "B.Tech Computer Science & Engineering (Cloud Computing & Automation)": VIT_CURRICULUM_DATA,
}

ALL_PROGRAMMES = {name for names in PROGRAMMES.values() for name in names}


# =========================================================
# DATABASE CONNECTION (SUPABASE POSTGRESQL)
# =========================================================

def get_db():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured in environment variables.")
    connection = psycopg2.connect(
        database_url,
        cursor_factory=psycopg2.extras.RealDictCursor
    )
    return connection


def init_db():
    try:
        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                subject TEXT NOT NULL,
                program TEXT DEFAULT '',
                curriculum_type TEXT DEFAULT '',
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

        cur.execute("ALTER TABLE notes ADD COLUMN IF NOT EXISTS curriculum_type TEXT DEFAULT ''")

        conn.commit()
        cur.close()
        conn.close()
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
    curriculum = {
        ctype: [subject for group in groups.values() for subject in group]
        for ctype, groups in VIT_CURRICULUM_DATA.items()
    }
    return render_template("subjects.html", curriculum=curriculum)


@app.route("/subjects/`")
def subject_detail(code):
    if "user_id" not in session:
        flash("Please login first to view notes and materials for this subject.", "error")
        return redirect(url_for("login", next=request.path))
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT notes.*, users.name AS author FROM notes JOIN users ON notes.user_id = users.id WHERE notes.subject ILIKE %s OR notes.content ILIKE %s ORDER BY notes.updated_at DESC",
        (f"%{code}%", f"%{code}%")
    )
    notes = cur.fetchall()
    cur.close()
    conn.close()
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

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM users WHERE email = %s",
        (email,)
    )
    user = cur.fetchone()

    if not user:
        dummy_password = generate_password_hash(str(uuid.uuid4()))
        cur.execute(
            """
            INSERT INTO users (name, email, password)
            VALUES (%s, %s, %s)
            RETURNING id, name, email
            """,
            (name, email, dummy_password)
        )
        user = cur.fetchone()
        conn.commit()

    cur.close()
    conn.close()

    session.permanent = True
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

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id
            FROM users
            WHERE email = %s
            """,
            (email,)
        )
        existing_user = cur.fetchone()

        if existing_user:
            cur.close()
            conn.close()
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

        cur.execute(
            """
            INSERT INTO users
            (
                name,
                email,
                password
            )
            VALUES (%s, %s, %s)
            """,
            (
                name,
                email,
                hashed_password
            )
        )
        conn.commit()
        cur.close()
        conn.close()

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
        if session.get("user_id"):
            return redirect(get_safe_next() or url_for("dashboard"))

    if request.method == "POST":
        email = (
            request.form["email"]
            .strip()
            .lower()
        )
        password = request.form["password"]

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM users
            WHERE email = %s
            """,
            (email,)
        )
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and check_password_hash(
            user["password"],
            password
        ):
            session.permanent = True
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
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM notes
        WHERE user_id = %s
        ORDER BY updated_at DESC
        """,
        (
            session["user_id"],
        )
    )
    notes = cur.fetchall()

    total_notes = len(notes)

    cur.execute(
        """
        SELECT COUNT(*) AS count
        FROM notes
        WHERE user_id = %s
        AND is_favorite = 1
        """,
        (
            session["user_id"],
        )
    )
    fav_res = cur.fetchone()
    favorite_count = fav_res['count'] if fav_res and 'count' in fav_res else 0

    cur.execute(
        """
        SELECT COUNT(*) AS count
        FROM notes
        WHERE user_id = %s
        AND is_public = 1
        """,
        (
            session["user_id"],
        )
    )
    pub_res = cur.fetchone()
    public_count = pub_res['count'] if pub_res and 'count' in pub_res else 0

    cur.close()
    conn.close()

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

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
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
            VALUES (%s, %s, %s, %s, %s, %s, %s)
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
        conn.commit()
        cur.close()
        conn.close()

        flash(
            "Note created successfully!",
            "success"
        )
        return redirect(
            url_for("dashboard")
        )

    return render_template(
        "create_note.html",
        programs=PROGRAMMES,
        curricula=VIT_CURRICULUM_DATA
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
        program = request.form.get("program", "").strip()
        curriculum_type = request.form.get("curriculum_type", "").strip()
        tags = request.form.get("tags", "").strip()
        content = request.form.get("content", "").strip()
        is_public = 1 if request.form.get("is_public") else 0
        uploaded_file = request.files.get("file")

        if not title:
            flash("Please enter a title for the note.", "error")
            return redirect(url_for("upload_note"))

        if program not in ALL_PROGRAMMES:
            flash("Please choose a programme from the list.", "error")
            return redirect(url_for("upload_note"))

        curriculum = PROGRAMME_CURRICULA.get(program)
        if curriculum:
            if curriculum_type not in curriculum:
                flash("Please choose a curriculum type for this programme.", "error")
                return redirect(url_for("upload_note"))

            subjects_in_type = {
                code: name
                for group in curriculum[curriculum_type].values()
                for code, name in group
            }
            subject_code = request.form.get("subject", "").strip()
            if subject_code not in subjects_in_type:
                flash("Please choose a subject from the list.", "error")
                return redirect(url_for("upload_note"))
            subject = f"{subject_code} - {subjects_in_type[subject_code]}"
        else:
            curriculum_type = ""
            subject = request.form.get("subject_text", "").strip()[:120]
            if not subject:
                flash("Please enter the subject name.", "error")
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
            flash(f"Supabase storage is not configured. Reason: {SUPABASE_ERROR}", "error")
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
            flash(f"Supabase Upload Failed ({type(e).__name__}): {str(e)}", "error")
            return redirect(url_for("upload_note"))

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO notes
            (
                user_id,
                title,
                subject,
                program,
                curriculum_type,
                content,
                tags,
                is_public,
                file_name,
                file_path,
                file_type
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session["user_id"],
                title,
                subject,
                program,
                curriculum_type,
                content,
                tags,
                is_public,
                safe_filename,
                database_file_path,
                file_type
            )
        )
        conn.commit()
        cur.close()
        conn.close()

        flash("Your note has been uploaded successfully to Supabase cloud storage!", "success")
        return redirect(url_for("dashboard"))

    return render_template(
        "upload_note.html",
        programs=PROGRAMMES,
        curricula=PROGRAMME_CURRICULA,
        max_mb=20
    )


# =========================================================
# VIEW NOTE
# =========================================================

@app.route("/notes/")
@login_required
def view_note(note_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            notes.*,
            users.name AS author
        FROM notes
        JOIN users
        ON notes.user_id = users.id
        WHERE notes.id = %s
        """,
        (
            note_id,
        )
    )
    note = cur.fetchone()
    cur.close()
    conn.close()

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

@app.route("/notes//edit", methods=["GET", "POST"])
@login_required
def edit_note(note_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM notes
        WHERE id = %s
        AND user_id = %s
        """,
        (
            note_id,
            session["user_id"]
        )
    )
    note = cur.fetchone()

    if not note:
        cur.close()
        conn.close()
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

        cur.execute(
            """
            UPDATE notes
            SET
                title = %s,
                subject = %s,
                program = %s,
                content = %s,
                tags = %s,
                is_public = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            AND user_id = %s
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
        conn.commit()
        cur.close()
        conn.close()

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

    cur.close()
    conn.close()

    return render_template(
        "edit_note.html",
        note=note,
        programs=PROGRAMMES
    )


# =========================================================
# DELETE NOTE
# =========================================================

@app.route("/notes//delete", methods=["POST"])
@login_required
def delete_note(note_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM notes
        WHERE id = %s
        AND user_id = %s
        """,
        (
            note_id,
            session["user_id"]
        )
    )
    conn.commit()
    cur.close()
    conn.close()

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

@app.route("/notes//favorite", methods=["POST"])
@login_required
def favorite_note(note_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT is_favorite
        FROM notes
        WHERE id = %s
        AND user_id = %s
        """,
        (
            note_id,
            session["user_id"]
        )
    )
    note = cur.fetchone()

    if note:
        new_value = (
            0
            if note["is_favorite"]
            else 1
        )
        cur.execute(
            """
            UPDATE notes
            SET is_favorite = %s
            WHERE id = %s
            AND user_id = %s
            """,
            (
                new_value,
                note_id,
                session["user_id"]
            )
        )
        conn.commit()

    cur.close()
    conn.close()

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

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            notes.*,
            users.name AS author
        FROM notes
        JOIN users
        ON notes.user_id = users.id
        WHERE
            (
                notes.user_id = %s
                OR notes.is_public = 1
            )
            AND
            (
                notes.title ILIKE %s
                OR notes.subject ILIKE %s
                OR notes.program ILIKE %s
                OR notes.content ILIKE %s
                OR notes.tags ILIKE %s
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
    )
    notes = cur.fetchall()
    cur.close()
    conn.close()

    return render_template(
        "public_notes.html",
        notes=notes,
        query=query,
        programs=PROGRAMMES
    )


# =========================================================
# PUBLIC VAULT
# =========================================================

@app.route("/vault")
@login_required
def vault():
    selected_program = request.args.get("program", "").strip()
    selected_subject = request.args.get("subject", "").strip()

    conn = get_db()
    cur = conn.cursor()
    
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
        query += " AND notes.program = %s"
        params.append(selected_program)

    if selected_subject:
        query += " AND notes.subject = %s"
        params.append(selected_subject)

    query += " ORDER BY notes.created_at DESC"

    cur.execute(query, params)
    notes = cur.fetchall()
    cur.close()
    conn.close()

    return render_template(
        "public_notes.html",
        notes=notes,
        query="",
        programs=PROGRAMMES,
        selected_program=selected_program,
        selected_subject=selected_subject
    )


# =========================================================
# AI TOOLS (WITH SUPABASE PDF FILE EXTRACTION SUPPORT)
# =========================================================

def get_ai_client():
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_KEY")
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
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT * FROM notes WHERE id = %s AND (user_id = %s OR is_public = 1)", (note_id, session["user_id"]))
            note = cur.fetchone()
            cur.close()
            conn.close()
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

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, title, subject FROM notes WHERE user_id = %s ORDER BY updated_at DESC", (session["user_id"],))
    user_notes = cur.fetchall()
    cur.close()
    conn.close()

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