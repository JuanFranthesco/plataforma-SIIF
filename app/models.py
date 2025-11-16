from app.extensions import db 
from datetime import datetime, timezone
from flask_login import UserMixin
from . import login_manager

# ===================================================================
# TELAS: Tela de Login e Tela de Perfil
# RESPONSÁVEIS: Equipe 2
# ===================================================================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(db.Model, UserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    matricula = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_admin = db.Column(db.Boolean, default=False)
    perfil = db.relationship('Perfil', backref='user', uselist=False, lazy=True)

    def set_password(self, password):
        """Cria um hash seguro da senha."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verifica se a senha fornecida bate com o hash."""
        return check_password_hash(self.password_hash, password)
    def __repr__(self): return f'<User {self.matricula}>'


class Perfil(db.Model):
    __tablename__ = 'perfil'
    id = db.Column(db.Integer, primary_key=True)
    curso = db.Column(db.String(100), nullable=True)
    campus = db.Column(db.String(100), nullable=True)
    bio = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    def __repr__(self): return f'<Perfil do usuário {self.user_id}>'

class Notificacao(db.Model):
    __tablename__ = 'notificacao'
    id = db.Column(db.Integer, primary_key=True)
    mensagem = db.Column(db.String(300), nullable=False)
    link_url = db.Column(db.String(300), nullable=True)
    lida = db.Column(db.Boolean, default=False)

    data_criacao = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    usuario_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    def __repr__(self): return f'<Notificação para {self.usuario_id}>'

# ===================================================================
# TELAS: Tela do Mapa e Tela de Divulgação
# RESPONSÁVEIS: Equipe 1
# ===================================================================

class PontoDeInteresse(db.Model):
    __tablename__ = 'ponto_de_interesse'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    tipo = db.Column(db.String(50), nullable=True)
    eventos = db.relationship('Evento', backref='local', lazy=True)
    def __repr__(self): return f'<Ponto {self.nome}>'

class Evento(db.Model):
    __tablename__ = 'evento'
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    data_hora_inicio = db.Column(db.DateTime, nullable=False)
    local_id = db.Column(db.Integer, db.ForeignKey('ponto_de_interesse.id'), nullable=True)
    organizador_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    def __repr__(self): return f'<Evento {self.titulo}>'

class Noticia(db.Model):
    __tablename__ = 'noticia'
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    conteudo = db.Column(db.Text, nullable=False)
    imagem_url = db.Column(db.String(300), nullable=True)
    arquivo_url = db.Column(db.String(300), nullable=True)
    link_externo = db.Column(db.String(300), nullable=True)
    campus = db.Column(db.String(100), nullable=True)
    categoria = db.Column(db.String(100), nullable=True)
    data_postagem = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    autor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f'<Notícia {self.titulo}>'


# ===================================================================
# TELA: Tela de Materiais
# RESPONSÁVEIS: Equipe 4
# ===================================================================

class Material(db.Model):
    __tablename__ = 'material'
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    arquivo_path = db.Column(db.String(300), nullable=False)

    data_upload = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    categoria = db.Column(db.String(100), nullable=True)
    autor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    def __repr__(self): return f'<Material {self.titulo}>'

# ===================================================================
# TELA: Tela de Fóruns
# RESPONSÁVEIS: Equipe 3
# ===================================================================

class Topico(db.Model):
    __tablename__ = 'topico'
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    conteudo = db.Column(db.Text, nullable=False)

    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    autor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    respostas = db.relationship('Resposta', backref='topico', lazy=True, cascade="all, delete-orphan")
    def __repr__(self): return f'<Topico {self.titulo}>'

class Resposta(db.Model):
    __tablename__ = 'resposta'
    id = db.Column(db.Integer, primary_key=True)
    conteudo = db.Column(db.Text, nullable=False)

    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    topico_id = db.Column(db.Integer, db.ForeignKey('topico.id'), nullable=False)
    autor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    def __repr__(self): return f'<Resposta ao tópico {self.topico_id}>'

class PostLike(db.Model):
    __tablename__ = 'post_like'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    topico_id = db.Column(db.Integer, db.ForeignKey('topico.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'topico_id', name='_user_topico_like_uc'),)
    def __repr__(self): return f'<Like do User {self.user_id} no Tópico {self.topico_id}>'

class PostSalvo(db.Model):
    __tablename__ = 'post_salvo'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    topico_id = db.Column(db.Integer, db.ForeignKey('topico.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'topico_id', name='_user_topico_save_uc'),)
    def __repr__(self): return f'<Post Salvo do User {self.user_id} (Tópico {self.topico_id})>'

# ===================================================================
# TELA: Tela de Suporte
# RESPONSÁVEIS: Equipe 3
# ===================================================================

class RelatoSuporte(db.Model):
    __tablename__ = 'relato_suporte'
    id = db.Column(db.Integer, primary_key=True)
    tipo_relato = db.Column(db.String(50), nullable=False)
    descricao = db.Column(db.Text, nullable=False)
  
    data_envio = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(50), default='Recebido')
    relator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) 
    def __repr__(self): return f'<Relato de Suporte #{self.id}>'

class FAQ(db.Model):
    __tablename__ = 'faq'
    id = db.Column(db.Integer, primary_key=True)
    pergunta = db.Column(db.String(255), nullable=False)
    resposta = db.Column(db.Text, nullable=False)
    categoria = db.Column(db.String(50), nullable=True)
    def __repr__(self): return f'<FAQ: {self.pergunta[:30]}>'

# ===================================================================
# TELA: Tela de Denúncias
# RESPONSÁVEIS: Equipe 4
# ===================================================================

class Denuncia(db.Model):
    __tablename__ = 'denuncia'
    id = db.Column(db.Integer, primary_key=True)
    tipo_denuncia = db.Column(db.String(50), nullable=False)
    descricao = db.Column(db.Text, nullable=False)

    data_envio = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(50), default='Recebida')
    denunciante_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    def __repr__(self): return f'<Denúncia #{self.id}>'
