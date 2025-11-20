from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, Length
from app.models import db, User

class LoginForm(FlaskForm):
    # O campo 'matricula' corresponde ao 'name' que usaremos no HTML
    matricula = StringField('Usuário', validators=[DataRequired()])
    password = PasswordField('Senha', validators=[DataRequired()])
    submit = SubmitField('Acessar')

class RegisterForm(FlaskForm):
    matricula = StringField('Matrícula', validators=[DataRequired()])
    name = StringField('Nome', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email(message="Email inválido.")])
    password = PasswordField('Senha', validators=[DataRequired()])
    password_confirm = PasswordField('Confirmar Senha', 
                                     validators=[DataRequired(), 
                                                 EqualTo('password', message='As senhas não conferem.')])
    
    submit = SubmitField('Registrar-se')

    # --- Validadores customizados ---

    def validate_matricula(self, matricula):
        """Verifica se a matrícula já existe no banco."""
        user = User.query.filter_by(matricula=matricula.data).first()

        if user:
            raise ValidationError('Esta matrícula já está em uso. Tente outra.')

    def validate_email(self, email):
        """Verifica se o e-mail já existe no banco."""
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Este e-mail já está em uso. Tente outro.')

class ProfileForm(FlaskForm):
    """
    Formulário para editar as informações do Perfil.
    Os nomes dos campos (curso, campus, bio) devem ser
    idênticos aos do modelo models.py/Perfil.
    """
    curso = StringField('Curso')
    campus = StringField('Campus')
    bio = TextAreaField('Sobre mim', validators=[Length(min=0, max=500)])
    foto = FileField('Atualizar Foto de Perfil', validators=[
        FileAllowed(['jpg', 'png', 'jpeg'], 'Apenas imagens jpg e png são permitidas!')
    ])
    banner = FileField('Alterar Banner', validators=[FileAllowed(['jpg', 'png'])])
    submit = SubmitField('Salvar Alterações')
