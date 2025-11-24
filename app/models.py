from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .extensions import db, login_manager

# ===================================================================
# LOGIN MANAGER
# ===================================================================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ===================================================================
# TABELAS DE ASSOCIAÇÃO (MUITOS-PARA-MUITOS)
# ===================================================================

# Quem participa da comunidade
membros_comunidade = db.Table('membros_comunidade',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('comunidade_id', db.Integer, db.ForeignKey('comunidade.id'), primary_key=True)
)

# Quem modera a comunidade (tem poderes de edição/exclusão)
moderadores_comunidade = db.Table('moderadores_comunidade',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('comunidade_id', db.Integer, db.ForeignKey('comunidade.id'), primary_key=True)
)


# ===================================================================
# USUÁRIOS E PERFIL
# ===================================================================

class User(db.Model, UserMixin):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    matricula = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    
    # Campos de Perfil
    foto_url = db.Column(db.String(255), nullable=True)
    campus = db.Column(db.String(50), nullable=True)

    # Relações com outros modelos
    perfil = db.relationship('Perfil', backref='user', uselist=False, lazy=True)
    
    # Comunidades que o usuário segue
    comunidades_seguidas = db.relationship('Comunidade', secondary=membros_comunidade, backref=db.backref('membros', lazy='dynamic'))
    
    # Solicitações de entrada em grupos privados
    solicitacoes = db.relationship('SolicitacaoParticipacao', backref='usuario', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.matricula}>'


class Perfil(db.Model):
    __tablename__ = 'perfil'
    id = db.Column(db.Integer, primary_key=True)
    curso = db.Column(db.String(100), nullable=True)
    bio = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    # Mantendo campos para compatibilidade se necessário
    foto_perfil = db.Column(db.String(120), nullable=False, default='default.png') 
    banner_perfil = db.Column(db.String(120), default='default_banner.jpg') 


class Notificacao(db.Model):
    __tablename__ = 'notificacao'
    id = db.Column(db.Integer, primary_key=True)
    mensagem = db.Column(db.String(300), nullable=False)
    link_url = db.Column(db.String(300), nullable=True)
    lida = db.Column(db.Boolean, default=False)
    data_criacao = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    usuario_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


# ===================================================================
# COMUNIDADES E GESTÃO AVANÇADA
# ===================================================================

class SolicitacaoParticipacao(db.Model):
    __tablename__ = 'solicitacao_participacao'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comunidade_id = db.Column(db.Integer, db.ForeignKey('comunidade.id'), nullable=False)
    data_solicitacao = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(20), default='Pendente') # Pendente, Aceito, Rejeitado


class ComunidadeTag(db.Model):
    """Tags (Flairs) para categorizar posts dentro da comunidade"""
    __tablename__ = 'comunidade_tag'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False)
    cor = db.Column(db.String(20), default='#6c757d') # Cor da etiqueta
    comunidade_id = db.Column(db.Integer, db.ForeignKey('comunidade.id'), nullable=False)


class AuditLog(db.Model):
    """Registro de ações de moderação (Quem fez o que)"""
    __tablename__ = 'audit_log'
    id = db.Column(db.Integer, primary_key=True)
    acao = db.Column(db.String(100), nullable=False)
    detalhes = db.Column(db.String(255), nullable=True)
    data = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    comunidade_id = db.Column(db.Integer, db.ForeignKey('comunidade.id'), nullable=False)
    autor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    # Relação para saber quem fez a ação
    autor = db.relationship('User', foreign_keys=[autor_id])


class Comunidade(db.Model):
    __tablename__ = 'comunidade'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)
    descricao = db.Column(db.String(300), nullable=False)
    
    # Organização
    categoria = db.Column(db.String(50), default='Geral') 
    tipo_acesso = db.Column(db.String(20), default='Público') 
    regras = db.Column(db.Text, nullable=True)
    
    # Identidade Visual Avançada
    imagem_url = db.Column(db.String(300), default='default_community.png') # Logo Redonda
    banner_url = db.Column(db.String(300), nullable=True) # Capa Retangular
    cor_tema = db.Column(db.String(20), default='#386641') # Cor Principal
    
    # Segurança e Moderação
    palavras_proibidas = db.Column(db.Text, nullable=True) # Lista separada por vírgula
    trancada = db.Column(db.Boolean, default=False) # Se True, ninguém posta
    
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    criador_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relacionamentos
    topicos = db.relationship('Topico', backref='comunidade', lazy=True)
    moderadores = db.relationship('User', secondary=moderadores_comunidade, backref=db.backref('comunidades_moderadas', lazy='dynamic'))
    solicitacoes = db.relationship('SolicitacaoParticipacao', backref='comunidade', lazy=True)
    tags = db.relationship('ComunidadeTag', backref='comunidade', lazy=True)
    logs = db.relationship('AuditLog', backref='comunidade', lazy=True)

    def __repr__(self):
        return f'<Comunidade {self.nome}>'


# ===================================================================
# FÓRUM (POSTS E RESPOSTAS)
# ===================================================================

class Topico(db.Model):
    __tablename__ = 'topico'

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    conteudo = db.Column(db.Text, nullable=False)
    
    # Campo para Imagem no Post
    imagem_post = db.Column(db.String(300), nullable=True) 
    
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    autor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Link opcional com comunidade
    comunidade_id = db.Column(db.Integer, db.ForeignKey('comunidade.id'), nullable=True)
    
    # Tag do post (Flair)
    tag_id = db.Column(db.Integer, db.ForeignKey('comunidade_tag.id'), nullable=True)
    tag = db.relationship('ComunidadeTag')
    
    # Relacionamento reverso para autor
    autor = db.relationship('User', backref='topicos_criados', lazy=True)

    # Relacionamentos
    respostas = db.relationship('Resposta', backref='topico', lazy=True, cascade="all, delete-orphan")
    likes = db.relationship('PostLike', backref='topico', lazy=True, cascade="all, delete-orphan")
    salvos = db.relationship('PostSalvo', backref='topico', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Topico {self.titulo}>'


class Resposta(db.Model):
    __tablename__ = 'resposta'

    id = db.Column(db.Integer, primary_key=True)
    conteudo = db.Column(db.Text, nullable=False)
    
    # Campo para Imagem no Comentário
    imagem_resposta = db.Column(db.String(300), nullable=True)
    
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    topico_id = db.Column(db.Integer, db.ForeignKey('topico.id'), nullable=False)
    autor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relacionamento reverso para autor
    autor = db.relationship('User', backref='respostas_criadas', lazy=True)
    
    # --- HIERARQUIA (ESCADINHA) ---
    parent_id = db.Column(db.Integer, db.ForeignKey('resposta.id'), nullable=True)
    
    filhos = db.relationship('Resposta', 
                             backref=db.backref('pai', remote_side=[id]), 
                             lazy=True, 
                             cascade="all, delete-orphan")

    # Likes no comentário
    likes = db.relationship('RespostaLike', backref='resposta', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Resposta {self.id}>'


# ===================================================================
# LIKES E SALVOS
# ===================================================================

class PostLike(db.Model):
    __tablename__ = 'post_like'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    topico_id = db.Column(db.Integer, db.ForeignKey('topico.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'topico_id', name='_user_topico_like_uc'),)

class RespostaLike(db.Model):
    __tablename__ = 'resposta_like'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    resposta_id = db.Column(db.Integer, db.ForeignKey('resposta.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'resposta_id', name='_user_resposta_like_uc'),)

class PostSalvo(db.Model):
    __tablename__ = 'post_salvo'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    topico_id = db.Column(db.Integer, db.ForeignKey('topico.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'topico_id', name='_user_topico_save_uc'),)

# ===================================================================
# MÓDULOS SECUNDÁRIOS (MANTIDOS)
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

class PontoDeInteresse(db.Model):
    __tablename__ = 'ponto_de_interesse'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    tipo = db.Column(db.String(50), nullable=True)
    eventos = db.relationship('Evento', backref='local', lazy=True)

class Evento(db.Model):
    __tablename__ = 'evento'
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    data_hora_inicio = db.Column(db.DateTime, nullable=False)
    local_id = db.Column(db.Integer, db.ForeignKey('ponto_de_interesse.id'), nullable=True)
    organizador_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

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

class RelatoSuporte(db.Model):
    __tablename__ = 'relato_suporte'
    id = db.Column(db.Integer, primary_key=True)
    tipo_relato = db.Column(db.String(50), nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    data_envio = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(50), default='Recebido')
    relator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

class FAQ(db.Model):
    __tablename__ = 'faq'
    id = db.Column(db.Integer, primary_key=True)
    pergunta = db.Column(db.String(255), nullable=False)
    resposta = db.Column(db.Text, nullable=False)
    categoria = db.Column(db.String(50), nullable=True)

class Denuncia(db.Model):
    __tablename__ = 'denuncia'
    id = db.Column(db.Integer, primary_key=True)
    tipo_denuncia = db.Column(db.String(50), nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    data_envio = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(50), default='Recebida')
    denunciante_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
