import os
from flask import Flask
from .extensions import db, migrate

db = SQLAlchemy()
login_manager = LoginManager()


def create_app(): 
    app = Flask(__name__)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    app.config['SECRET_KEY'] = 'aQ1!zW2@sX3#eD4$rF5%tG6^yH7&uJ8*iK9(oL0)pZ_c-Vb=n+M<,l.>'
    
    UPLOAD_PATH = os.path.join(app.root_path, 'static', 'uploads')
    os.makedirs(UPLOAD_PATH, exist_ok=True) 
    app.config['UPLOAD_FOLDER'] = UPLOAD_PATH
    
    db.init_app(app)
    login_manager.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    
    with app.app_context():
        from app import models 
        
    return app