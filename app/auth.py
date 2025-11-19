import os
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required
from requests_oauthlib import OAuth2Session
from app.models import User, db
from app.forms import LoginForm, RegisterForm

auth_bp = Blueprint('auth', __name__)

# --- CONFIGURAÇÕES DO SUAP ---
# Em produção, coloque isso em variáveis de ambiente (os.environ)
SUAP_CLIENT_ID = 'KKX443djD2LvDhApYTXDJIlCesqD2xGWuPhlZjqN'
SUAP_CLIENT_SECRET = 'CqdW2HZUsO5RwXrft3e1c4nVIi06iDgIscjbpnOqDWvivokJxxVzDqfeQWAChF56ZujAEFuFYekX18XdoDbS26HFJTGrap28h8d5uU34yjMcxaULbbYBAsrH4wZTqCZ8'
SUAP_BASE_URL = 'https://suap.ifrn.edu.br' # Ex: https://suap.ifrn.edu.br
SUAP_AUTH_URL = f'{SUAP_BASE_URL}/o/authorize/'
SUAP_TOKEN_URL = f'{SUAP_BASE_URL}/o/token/'
SUAP_API_URL = f'{SUAP_BASE_URL}/api/eu/' # Endpoint que retorna dados do usuário
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://127.0.0.1:5000/suap/callback")
# Isso permite rodar OAuth em localhost sem HTTPS (apenas para desenvolvimento)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Se o usuário já está logado, manda para a home
    if current_user.is_authenticated:
        return redirect(url_for('main.tela_inicial'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(matricula=form.matricula.data).first()
        # Verifica senha apenas se o usuário tiver senha (usuários SUAP podem não ter)
        if user and user.password_hash and user.check_password(form.password.data):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.tela_inicial'))
        else:
            flash('Matrícula ou senha inválida.', 'danger')
            
    return render_template('tela_login.html', form=form)

@auth_bp.route('/login/suap')
def login_suap():
    # --- CORREÇÃO DE SEGURANÇA 1: LIMPEZA ---
    # Antes de começar um novo login OAuth, garantimos que não há ninguem logado
    if current_user.is_authenticated:
        logout_user()
    
    # Limpa completamente a sessão (remove dados antigos, states velhos, etc)
    session.clear()
    
    # Inicia o fluxo
    suap = OAuth2Session(SUAP_CLIENT_ID, redirect_uri=REDIRECT_URI)
    authorization_url, state = suap.authorization_url(SUAP_AUTH_URL)
    
    # Salva o novo state limpo
    session['oauth_state'] = state
    return redirect(authorization_url)

@auth_bp.route('/suap/callback')
def suap_callback():
    try:
        if 'oauth_state' not in session:
            flash('Sessão inválida. Tente o login novamente.', 'danger')
            return redirect(url_for('auth.login'))
        
        suap = OAuth2Session(SUAP_CLIENT_ID, state=session.get('oauth_state'), redirect_uri=REDIRECT_URI)
        
        # 1. Troca o código de autorização pelo token de acesso
        token = suap.fetch_token(
            SUAP_TOKEN_URL,
            client_secret=SUAP_CLIENT_SECRET,
            authorization_response=request.url
        )
        
        # 2. Usa o token para pegar os dados do aluno/servidor
        user_data = suap.get(SUAP_API_URL).json()
        print(user_data)
        # Exemplo de resposta do SUAP: {'matricula': '2020...', 'nome_usual': 'Fulano', 'email': '...'}
        matricula_suap = user_data.get('identificacao') # Ou 'matricula', depende da versão do SUAP da sua escola
        email_suap = user_data.get('email')
        nome_suap = user_data.get('nome')
        foto_suap = user_data.get('foto')
        campus_suap = user_data.get('campus')
        if user_data.get("tipo_usuario") == "Aluno":
            admin = False
        else:
            admin = True


        if not matricula_suap:
            flash('Erro ao ler dados do SUAP.', 'danger')
            return redirect(url_for('auth.login'))

        # 3. Verifica se o usuário já existe no banco local
        user = User.query.filter_by(matricula=matricula_suap).first()

        if not user:
            # Se não existe, cria o usuário automaticamente (First-time login)
            user = User(
                matricula=matricula_suap,
                email=email_suap,
                name=nome_suap,
                password_hash=None, # Usuário SUAP não tem senha local
                is_admin=admin,
                foto_url=foto_suap,
                campus=campus_suap
            )
            db.session.add(user)
            db.session.commit()
        
        # 4. Loga o usuário no Flask-Login
        login_user(user)
        flash('Login via SUAP realizado com sucesso!', 'success')
        return redirect(url_for('main.tela_inicial'))

    except Exception as e:
        flash(f'Erro na autenticação SUAP: {str(e)}', 'danger')
        return redirect(url_for('auth.login'))


@auth_bp.route('/logout')
@login_required  # Só pode deslogar quem está logado
def logout():
    logout_user()
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    
    if form.validate_on_submit():
        try:
            # 1. Cria a nova instância do usuário
            new_user = User(
                matricula=form.matricula.data,
                email=form.email.data,
                name=form.name.data,
            )
            
            # 2. Define o hash da senha
            new_user.set_password(form.password.data)
            
            # 3. Adiciona e salva no banco de dados
            db.session.add(new_user)
            db.session.commit()
            
            flash('Conta criada com sucesso! Por favor, faça o login.', 'success')
            return redirect(url_for('auth.login'))
        
        except Exception as e:
            db.session.rollback() # Desfaz em caso de erro
            flash(f'Erro ao criar conta: {e}', 'danger')

    # Se for GET ou se a validação falhar, renderiza o template de registro
    return render_template('register.html', form=form)
