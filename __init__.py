import os
from flask import Flask
from .extensions import db, migrate

def create_app(): 
    app = Flask(__name__)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    #tive q criar essa chave para poder usar o flash message
    app.config['SECRET_KEY'] = 'qlqr-coisa-aq-da-crt'
    
    UPLOAD_PATH = os.path.join(app.root_path, 'static', 'uploads')
    os.makedirs(UPLOAD_PATH, exist_ok=True) 
    app.config['UPLOAD_FOLDER'] = UPLOAD_PATH
    
    db.init_app(app)
    migrate.init_app(app, db) # <-- O "robô" é ligado aqui

    
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    
    with app.app_context():
        from app import models 

    
    return app