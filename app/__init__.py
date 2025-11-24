import os
from datetime import timedelta
from flask import Flask

def create_app():
    app = Flask(__name__, instance_relative_config=False)

    # --------------------------
    # Configurações principais
    # --------------------------
    # Banco de Dados
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL',
        'sqlite:///' + os.path.join(app.root_path, 'site.db')
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Chave Secreta (Importante para sessões e segurança)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-this')

    # Configuração de Sessão
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
    app.config['SESSION_PERMANENT'] = True

    # --- [SEGURANÇA DE UPLOAD - NOVO] ---
    # Limita o tamanho máximo do upload. 
    # 16 * 1024 * 1024 = 16 Megabytes.
    # Se o arquivo for maior que isso, o Flask rejeitará com erro 413 (Request Entity Too Large).
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 
    
    # Pasta de Uploads
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
    
    # Configuração do Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login' # Redireciona para cá se não estiver logado
    login_manager.login_message_category = 'info'

    # Carregador de usuário para o Flask-Login
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        # Retorna o usuário do banco ou None se não achar
        return User.query.get(int(user_id))

    # --------------------------
    # Registrar Blueprints
    # --------------------------
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
    # Configuração do Banco de Dados (Criação de Tabelas e Admin)
    # --------------------------
    with app.app_context():
        db.create_all()
        
        # Verifica e cria usuário admin padrão se não existir
        admin_exists = User.query.filter_by(matricula="1234").first()
        if not admin_exists:
            print("Criando usuário administrador padrão...")
            admin_user = User(
                matricula="1234",
                is_admin=True,
                email="admin@siif.com", 
                name="Administrador",
                password_hash="admin" # Nota: Em produção, use hash real!
            )
            # Se o seu modelo User tiver método set_password, use-o aqui:
            if hasattr(admin_user, 'set_password'):
                admin_user.set_password("admin")
                
            db.session.add(admin_user)
            db.session.commit()
            print("Usuário administrador '1234' criado com sucesso.")

    return app