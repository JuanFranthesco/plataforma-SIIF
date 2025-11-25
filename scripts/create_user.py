import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.extensions import db
from app.models import User

def create_user(matricula, email, name, password, is_admin=False):
    app = create_app()
    with app.app_context():
        user = User(
            matricula=matricula,
            email=email,
            name=name,
            is_admin=is_admin
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f"User {name} with email {email} created successfully.")

if __name__ == "__main__":
    # Replace values below with desired new user data
    matricula = "123"
    email = "newuser@teste.com"
    name = "teste"
    password = "123"  # Replace with desired password
    is_admin = False

    create_user(matricula, email, name, password, is_admin)
