# app/__init__.py
import os
from flask import Flask

def create_app():
    app = Flask(__name__, instance_relative_config=False)

    # --------------------------
    # Configurações principais
    # --------------------------
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL',
        'sqlite:///' + os.path.join(app.root_path, 'site.db')
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-this')

    # Uploads
    app.config['UPLOAD_FOLDER'] = os.environ.get(
        'UPLOAD_FOLDER',
        os.path.join(app.root_path, 'static', 'uploads')
    )
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Configurações do fórum
    app.config['FORUM_TOPICS_PER_PAGE'] = int(os.environ.get('FORUM_TOPICS_PER_PAGE', 20))
    app.config['FORUM_POSTS_PER_PAGE'] = int(os.environ.get('FORUM_POSTS_PER_PAGE', 30))
    app.config['FORUM_MIN_REPLY_INTERVAL'] = float(os.environ.get('FORUM_MIN_REPLY_INTERVAL', 2.0))

    # --------------------------
    # Inicializa extensões
    # --------------------------
    from .extensions import db, migrate, login_manager
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    # --- [CORREÇÃO IMPORTANTE AQUI] ---
    # O Flask-Login precisa saber como buscar o usuário pelo ID
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        # Retorna o usuário do banco ou None se não achar
        return User.query.get(int(user_id))
    # ----------------------------------

    # Registrar blueprints
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    try:
        from app.auth import auth_bp
        app.register_blueprint(auth_bp)
    except ImportError:
        pass

    try:
        from app.api import api
        app.register_blueprint(api)
    except ImportError:
        pass

    # --------------------------
    # Criar tabelas no DB
    # --------------------------
    with app.app_context():
        # O import já foi feito acima, mas não tem problema repetir ou usar o já importado
        db.create_all()
        admin_exists = User.query.filter_by(matricula="1234").first()
        if not admin_exists:
            print("Criando usuário administrador padrão...")
            admin_user = User(
                matricula="1234",
                is_admin=True,
                email="admin@siif.com", 
                name="Administrador",
                password_hash="admin" 
            )
            # Nota: Idealmente use set_password aqui também se o modelo exigir hash
            admin_user.set_password("admin") 
            db.session.add(admin_user)
            db.session.commit()
            print("Usuário administrador '1234' criado com sucesso.")

    return app