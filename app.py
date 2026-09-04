import os
import sqlite3
import uuid
from functools import wraps

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

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


# =========================================================
# CONFIGURATION
# =========================================================

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    "dev-secret-change-this"
)

# Always use the folder where app.py is located
BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DATABASE = os.path.join(
    BASE_DIR,
    "database.db"
)


# =========================================================
# FILE UPLOAD CONFIGURATION
# =========================================================

UPLOAD_FOLDER = os.path.join(
    BASE_DIR,
    "uploads"
)

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

# Maximum file size = 20 MB
app.config["MAX_CONTENT_LENGTH"] = (
    20 * 1024 * 1024
)


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

    db = get_db()

    # =====================================================
    # USERS
    # =====================================================

    db.execute("""
        CREATE TABLE IF NOT EXISTS users (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            email TEXT UNIQUE NOT NULL,

            password TEXT NOT NULL,

            created_at
            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =====================================================
    # NOTES
    # =====================================================

    db.execute("""
        CREATE TABLE IF NOT EXISTS notes (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL,

            title TEXT NOT NULL,

            subject TEXT NOT NULL,

            content TEXT NOT NULL,

            tags TEXT DEFAULT '',

            is_public INTEGER DEFAULT 0,

            is_favorite INTEGER DEFAULT 0,

            file_name TEXT DEFAULT '',

            file_path TEXT DEFAULT '',

            file_type TEXT DEFAULT '',

            created_at
            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            updated_at
            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id)
            REFERENCES users(id)

            ON DELETE CASCADE
        )
    """)

    # =====================================================
    # UPDATE OLD DATABASE
    # =====================================================

    existing_columns = [
        row["name"]
        for row in db.execute(
            "PRAGMA table_info(notes)"
        ).fetchall()
    ]

    if "file_name" not in existing_columns:

        db.execute("""
            ALTER TABLE notes
            ADD COLUMN file_name TEXT DEFAULT ''
        """)

    if "file_path" not in existing_columns:

        db.execute("""
            ALTER TABLE notes
            ADD COLUMN file_path TEXT DEFAULT ''
        """)

    if "file_type" not in existing_columns:

        db.execute("""
            ALTER TABLE notes
            ADD COLUMN file_type TEXT DEFAULT ''
        """)

    db.commit()

    db.close()

    # =====================================================
    # CREATE UPLOAD FOLDERS
    # =====================================================

    os.makedirs(
        PDF_FOLDER,
        exist_ok=True
    )

    os.makedirs(
        IMAGE_FOLDER,
        exist_ok=True
    )


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
                url_for("login")
            )

        return function(
            *args,
            **kwargs
        )

    return wrapper


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


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
                url_for("dashboard")
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
                content,
                tags,
                is_public
            )

            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                title,
                subject,
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
        "create_note.html"
    )


# =========================================================
# UPLOAD PDF / IMAGE
# =========================================================

@app.route(
    "/notes/upload",
    methods=["GET", "POST"]
)
@login_required
def upload_note():

    if request.method == "POST":

        title = (
            request.form.get(
                "title",
                ""
            )
            .strip()
        )

        subject = (
            request.form.get(
                "subject",
                ""
            )
            .strip()
        )

        tags = (
            request.form.get(
                "tags",
                ""
            )
            .strip()
        )

        content = (
            request.form.get(
                "content",
                ""
            )
            .strip()
        )

        is_public = (
            1
            if request.form.get("is_public")
            else 0
        )

        uploaded_file = request.files.get(
            "file"
        )

        # -------------------------------------------------
        # VALIDATION
        # -------------------------------------------------

        if not title or not subject:

            flash(
                "Title and subject are required.",
                "error"
            )

            return redirect(
                url_for("upload_note")
            )

        if (
            not uploaded_file
            or not uploaded_file.filename
        ):

            flash(
                "Please select a PDF or image.",
                "error"
            )

            return redirect(
                url_for("upload_note")
            )

        original_filename = (
            uploaded_file.filename
        )

        if "." not in original_filename:

            flash(
                "Invalid file.",
                "error"
            )

            return redirect(
                url_for("upload_note")
            )

        extension = (
            original_filename
            .rsplit(".", 1)[1]
            .lower()
        )

        # -------------------------------------------------
        # DETERMINE TYPE
        # -------------------------------------------------

        if extension in ALLOWED_PDF_EXTENSIONS:

            file_type = "pdf"

            save_folder = PDF_FOLDER

            folder_name = "pdfs"

        elif extension in ALLOWED_IMAGE_EXTENSIONS:

            file_type = "image"

            save_folder = IMAGE_FOLDER

            folder_name = "images"

        else:

            flash(
                "Only PDF, PNG, JPG, JPEG, GIF and WEBP files are allowed.",
                "error"
            )

            return redirect(
                url_for("upload_note")
            )

        # -------------------------------------------------
        # SECURE FILENAME
        # -------------------------------------------------

        safe_filename = secure_filename(
            original_filename
        )

        if not safe_filename:

            flash(
                "Invalid filename.",
                "error"
            )

            return redirect(
                url_for("upload_note")
            )

        # -------------------------------------------------
        # UNIQUE FILE NAME
        # -------------------------------------------------

        extension_with_dot = os.path.splitext(
            safe_filename
        )[1]

        unique_filename = (
            str(uuid.uuid4())
            + extension_with_dot
        )

        full_file_path = os.path.join(
            save_folder,
            unique_filename
        )

        # -------------------------------------------------
        # SAVE FILE
        # -------------------------------------------------

        uploaded_file.save(
            full_file_path
        )

        # -------------------------------------------------
        # DATABASE PATH
        # IMPORTANT:
        # Always use "/" for web paths.
        # -------------------------------------------------

        database_file_path = (
            folder_name
            + "/"
            + unique_filename
        )

        # -------------------------------------------------
        # SAVE DATABASE RECORD
        # -------------------------------------------------

        db = get_db()

        db.execute(
            """
            INSERT INTO notes
            (
                user_id,
                title,
                subject,
                content,
                tags,
                is_public,
                file_name,
                file_path,
                file_type
            )

            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                title,
                subject,
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

        flash(
            "Your note has been uploaded successfully!",
            "success"
        )

        return redirect(
            url_for("dashboard")
        )

    return render_template(
        "upload_note.html"
    )


# =========================================================
# SERVE UPLOADED FILES
# =========================================================

@app.route(
    "/uploads/<path:filename>"
)
@login_required
def uploaded_file(filename):

    # Convert Windows path separators
    # into browser-compatible separators.
    filename = filename.replace(
        "\\",
        "/"
    )

    # Remove any accidental leading slash.
    filename = filename.lstrip("/")

    return send_from_directory(
        UPLOAD_FOLDER,
        filename
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
        note=note
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

    note = db.execute(
        """
        SELECT file_path
        FROM notes

        WHERE id = ?

        AND user_id = ?
        """,
        (
            note_id,
            session["user_id"]
        )
    ).fetchone()

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

    # Delete attached physical file
    if note and note["file_path"]:

        clean_path = (
            note["file_path"]
            .replace("\\", "/")
            .lstrip("/")
        )

        physical_path = os.path.join(
            UPLOAD_FOLDER,
            *clean_path.split("/")
        )

        if os.path.exists(
            physical_path
        ):

            try:
                os.remove(
                    physical_path
                )
            except OSError:
                pass

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
# SEARCH
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
            f"%{query}%"
        )
    ).fetchall()

    db.close()

    return render_template(
        "public_notes.html",
        notes=notes,
        query=query
    )


# =========================================================
# PUBLIC VAULT
# =========================================================

@app.route("/vault")
@login_required
def vault():

    db = get_db()

    notes = db.execute(
        """
        SELECT
            notes.*,
            users.name AS author

        FROM notes

        JOIN users
        ON notes.user_id = users.id

        WHERE notes.is_public = 1

        ORDER BY notes.created_at DESC
        """
    ).fetchall()

    db.close()

    return render_template(
        "public_notes.html",
        notes=notes,
        query=""
    )


# =========================================================
# AI
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
            "Add your OPENAI_API_KEY to the .env file."
        )

    try:

        response = client.responses.create(
            model="gpt-5.6",
            input=prompt
        )

        return response.output_text

    except Exception as error:

        return (
            "AI request failed: "
            + str(error)
        )


# =========================================================
# AI PAGE
# =========================================================

@app.route(
    "/ai",
    methods=["GET", "POST"]
)
@login_required
def ai_tools():

    result = None

    if request.method == "POST":

        content = (
            request.form.get(
                "content",
                ""
            )
            .strip()
        )

        action = request.form.get(
            "action"
        )

        if not content:

            flash(
                "Please enter some study material.",
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

    return render_template(
        "ai.html",
        result=result
    )


# =========================================================
# FILE TOO LARGE
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
# START APPLICATION
# =========================================================

if __name__ == "__main__":

    init_db()

    app.run(
        debug=True
    )