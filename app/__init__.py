import os
from flask import Flask
from .extensions import db, login_manager, migrate

def create_app():
   app = Flask(__name__, static_folder='static', template_folder='templates')

   app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
   app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
   app.config['SECRET_KEY'] = 'aQ1!zW2@sX3#eD4$rF5%tG6^yH7&uJ8*iK9(oL0)pZ_c-Vb=n+M<,l.>'

   upload_path = os.path.join(app.root_path, 'static', 'uploads')
   os.makedirs(upload_path, exist_ok=True)
   app.config['UPLOAD_FOLDER'] = upload_path
   db.init_app(app)
   login_manager.init_app(app)
   login_manager.login_view = 'auth.login'
   login_manager.login_message_category = 'info'

   from app.models import User
   
   @login_manager.user_loader
   def load_user(user_id):
      return User.query.get(int(user_id))

   from app.routes import main_bp
   app.register_blueprint(main_bp)

   from app.api import api
   app.register_blueprint(api)

   from app.auth import auth_bp
   app.register_blueprint(auth_bp)

   with app.app_context():
      from app import models
      db.create_all()

   return app
