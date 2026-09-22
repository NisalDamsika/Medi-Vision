"""
Medi Vision -- No-Show Prediction Prototype

"""

import bcrypt


def hash_password(plain_password: str) -> str:
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


def login(username: str, password: str):
    """
    Check credentials against the staff table.
    Returns the staff row (as a dict) if valid, otherwise None.
    Import is done inside the function to avoid a circular import with database.py.
    """
    import database

    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM staff WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()

    if row is None:
        return None

    if verify_password(password, row["password_hash"]):
        return dict(row)

    return None


def username_exists(username: str) -> bool:
    import database

    conn = database.get_connection()
    row = conn.execute("SELECT 1 FROM staff WHERE username = ?", (username,)).fetchone()
    conn.close()
    return row is not None


def signup(username: str, password: str, full_name: str, role: str):
    """
    Create a new staff account. Returns (success: bool, message: str).
    """
    import database

    username = username.strip()
    full_name = full_name.strip()

    if not username or not password or not full_name:
        return False, "All fields are required."
    if len(password) < 6:
        return False, "Password must be at least 6 characters long."
    if username_exists(username):
        return False, "This username is already taken."

    conn = database.get_connection()
    conn.execute(
        "INSERT INTO staff (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
        (username, hash_password(password), full_name, role),
    )
    conn.commit()
    conn.close()
    return True, "Account created successfully. You can now log in."
