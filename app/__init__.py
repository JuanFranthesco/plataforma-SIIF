import os
from datetime import timedelta
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix # <--- IMPORTANTE

def create_app():
    app = Flask(__name__, instance_relative_config=False)

    # --------------------------
    # CONFIGURAÇÃO CRÍTICA PARA O RENDER
    # --------------------------
    # O Render usa Load Balancers. Sem isso, o Flask gera links 'http' 
    # em vez de 'https', quebrando o Login do SUAP.
    app.wsgi_app = ProxyFix(
        app.wsgi_app, 
        x_for=1, 
        x_proto=1, 
        x_host=1, 
        x_prefix=1
    )

    # --------------------------
    # Configurações principais
    # --------------------------
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL',
        'sqlite:///' + os.path.join(app.root_path, 'site.db')
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Chave Secreta
    # No Render: Crie a variável de ambiente SECRET_KEY com um valor aleatório longo.
    # Se não criar, ele usa o valor inseguro abaixo (bom só para teste local).
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-this')

    # Configuração de Sessão
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
    app.config['SESSION_PERMANENT'] = True
    
    # Segurança de Cookie (Obrigatório para OAuth em Produção)
    # Só ativa se não estiver em modo debug/local
    if os.environ.get('FLASK_ENV') != 'development':
        app.config['SESSION_COOKIE_SECURE'] = True   # Só envia cookie via HTTPS
        app.config['SESSION_COOKIE_HTTPONLY'] = True # JS não lê o cookie
        app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # --- [SEGURANÇA DE UPLOAD] ---
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 
    
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

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
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
    # Banco de Dados
    # --------------------------
    with app.app_context():
        db.create_all()
        
        # Cria admin se não existir
        if not User.query.filter_by(matricula="1234").first():
            print("Criando usuário administrador padrão...")
            admin_user = User(
                matricula="1234",
                is_admin=True,
                email="admin@siif.com", 
                name="Administrador",
                password_hash="admin" 
            )
            if hasattr(admin_user, 'set_password'):
                admin_user.set_password("admin")
                
            db.session.add(admin_user)
            db.session.commit()

    return app