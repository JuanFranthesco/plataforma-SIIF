from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required
from app.models import User, db
from app.forms import LoginForm, RegisterForm

# Criamos o blueprint 'auth'
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    
    if form.validate_on_submit():
        # 1. Encontra o usuário pela matrícula
        user = User.query.filter_by(matricula=form.matricula.data).first()

        # 2. Verifica se o usuário existe e se a senha está correta
        if user and user.check_password(form.password.data):
            # 3. Registra o usuário como logado
            login_user(user)
            
            # Pega a página que o usuário tentou acessar antes (se houver)
            next_page = request.args.get('next')
            
            # Redireciona para a 'next_page' ou para a tela inicial
            return redirect(next_page or url_for('main.tela_inicial'))
        else:
            # 4. Se der erro, exibe uma mensagem
            flash('Matrícula ou senha inválida. Tente novamente.', 'danger')

    # Se for um GET, apenas renderiza o template de login
    return render_template('tela_login.html', form=form)


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
                email=form.email.data
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
