"""أوامر الإدارة من سطر الأوامر.

  python manage.py create-admin     إنشاء حساب أدمن (الكوست كنترول)
  python manage.py ensure-admin     إنشاء حساب أدمن فقط لو لا يوجد أدمن
  python manage.py migrate          تطبيق تحديثات قاعدة البيانات
  python manage.py unlock USERNAME  فك قفل حساب
"""
import getpass
import sys

from app import create_app
from app.auth import EMAIL_RE, USERNAME_RE, AuthError, create_user, password_problems
from app.db import connect, migrate


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    app = create_app()
    cmd = argv[1]
    with app.app_context():
        db = connect(app.config["DATABASE"])
        if cmd == "migrate":
            print("applied:", migrate(db) or "nothing")
        elif cmd == "ensure-admin" and db.execute("SELECT 1 FROM users WHERE role = 'admin'").fetchone():
            print("Admin account exists.")
        elif cmd in ("create-admin", "ensure-admin"):
            print("Create the first admin account (Cost Control)")
            print("You can write the full name in Arabic later from the platform: Accounts > your account.")
            full_name = input("Full name (English): ").strip()
            while True:
                username = input("Username (lowercase letters/numbers, e.g. m.algebaly): ").strip().lower()
                if USERNAME_RE.match(username):
                    break
                print("  Use 3-32 lowercase English letters, numbers, dot, dash or underscore.")
            while True:
                email = input("Email: ").strip()
                if EMAIL_RE.match(email):
                    break
                print("  Invalid email.")
            print("Password: at least 10 characters, letters and numbers, not containing the username.")
            print("(Nothing appears on screen while you type the password. This is normal.)")
            while True:
                pw = getpass.getpass("Password: ")
                if password_problems(pw, username):
                    print("  Password too weak. Try again.")
                    continue
                if pw != getpass.getpass("Confirm password: "):
                    print("  Passwords do not match. Try again.")
                    continue
                break
            try:
                uid, code, _ = create_user(db, username=username, email=email, full_name=full_name,
                                           role="admin", password=pw)
            except AuthError:
                print("Could not create the account: the username or email may already exist, or the name is too short.")
                return 1
            print(f"Admin account created: {code} / username: {username}")
        elif cmd == "unlock" and len(argv) > 2:
            n = db.execute("UPDATE users SET locked_until = NULL, failed_attempts = 0 WHERE username = ?",
                           (argv[2].lower(),)).rowcount
            print("Account unlocked." if n else "Account not found.")
        else:
            print(__doc__)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
