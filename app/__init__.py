import os
from datetime import timedelta
from flask import Flask, render_template_string
from werkzeug.middleware.proxy_fix import ProxyFix  # CRÍTICO PARA O RENDER

# Importa as extensões (certifique-se que o arquivo extensions.py existe)
from .extensions import db, migrate, login_manager, limiter


def create_app():
    app = Flask(__name__, instance_relative_config=False)

    # --------------------------
    # 1. CONFIGURAÇÃO CRÍTICA PARA O RENDER (HTTPS)
    # --------------------------
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,
        x_proto=1,
        x_host=1,
        x_prefix=1
    )

    # --------------------------
    # 2. BANCO DE DADOS (CORREÇÃO POSTGRESQL)
    # --------------------------
    # Pega a URL do banco do ambiente ou usa SQLite local
    db_url = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(app.root_path, 'site.db'))

    # O Render entrega 'postgres://', mas o SQLAlchemy exige 'postgresql://'
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # --------------------------
    # 3. SEGURANÇA E SESSÃO
    # --------------------------
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-this-in-prod')
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)
    app.config['SESSION_PERMANENT'] = True

    # Configurações de Cookie Seguro (Só ativa se NÃO estiver em modo debug)
    if not app.debug:
        app.config['SESSION_COOKIE_SECURE'] = True  # Só envia cookie via HTTPS
        app.config['SESSION_COOKIE_HTTPONLY'] = True  # JS não lê o cookie
        app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # --------------------------
    # 4. UPLOADS E OUTRAS CONFIGS
    # --------------------------
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limite

    app.config['UPLOAD_FOLDER'] = os.environ.get(
        'UPLOAD_FOLDER',
        os.path.join(app.root_path, 'static', 'uploads')
    )
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Configurações do Fórum
    app.config['FORUM_TOPICS_PER_PAGE'] = int(os.environ.get('FORUM_TOPICS_PER_PAGE', 20))
    app.config['FORUM_POSTS_PER_PAGE'] = int(os.environ.get('FORUM_POSTS_PER_PAGE', 30))
    app.config['FORUM_MIN_REPLY_INTERVAL'] = float(os.environ.get('FORUM_MIN_REPLY_INTERVAL', 2.0))

    # --------------------------
    # 5. INICIALIZAÇÃO DE EXTENSÕES
    # --------------------------
    db.init_app(app)
    migrate.init_app(app, db)

    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    limiter.init_app(app)

    # Importa o User APÓS inicializar o db para evitar ciclo
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # --------------------------
    # 6. TRATAMENTO DE ERROS (RATE LIMIT)
    # --------------------------
    @app.errorhandler(429)
    def ratelimit_handler(e):
        error_template = '''
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Limite Atingido - SIIF</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; }
                .error-container { background: rgba(255, 255, 255, 0.98); padding: 60px; border-radius: 20px; text-align: center; max-width: 600px; }
                .error-code { font-size: 100px; font-weight: bold; color: #667eea; margin: 0; }
            </style>
        </head>
        <body>
            <div class="error-container">
                <h1 class="error-code">429</h1>
                <h2>Limite de Requisições Atingido</h2>
                <p>Muitas tentativas. Aguarde um momento.</p>
                <a href="/" class="btn btn-primary">Voltar</a>
            </div>
        </body>
        </html>
        '''
        return render_template_string(error_template), 429

    # --------------------------
    # 7. REGISTRO DE BLUEPRINTS
    # --------------------------
    # Removemos o try/except para que erros de importação apareçam no log e você saiba se algo quebrar
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    from app.auth import auth_bp
    app.register_blueprint(auth_bp)

    from app.api import api
    app.register_blueprint(api)

    # --------------------------
    # 8. CRIAÇÃO DO ADMIN (CORRIGIDO)
    # --------------------------
    with app.app_context():
        db.create_all()

        # Verifica se admin existe, se não, cria
        if not User.query.filter_by(matricula="1234").first():
            print("--- CRIANDO USUÁRIO ADMINISTRADOR PADRÃO ---")
            admin_user = User(
                matricula="1234",
                is_admin=True,
                email="admin@siif.com",
                name="Administrador",
                tipo_usuario="Servidor"  # Ajuste conforme seu model
            )
            # Define a senha corretamente usando o hash
            admin_user.set_password("admin")

            db.session.add(admin_user)
            db.session.commit()
            print("--- ADMIN CRIADO COM SUCESSO ---")

    return app
