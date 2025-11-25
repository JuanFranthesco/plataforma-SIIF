# app/models.py
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
# TABELAS DE ASSOCIAÇÃO (NOVAS - PARA COMUNIDADES)
# ===================================================================

# Tabela para saber quem segue qual comunidade
membros_comunidade = db.Table('membros_comunidade',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('comunidade_id', db.Integer, db.ForeignKey('comunidade.id'), primary_key=True)
)

# Tabela para saber quem são os moderadores
moderadores_comunidade = db.Table('moderadores_comunidade',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('comunidade_id', db.Integer, db.ForeignKey('comunidade.id'), primary_key=True)
)

# Tabela associativa para Tags de Materiais
material_tags = db.Table('material_tags',
    db.Column('material_id', db.Integer, db.ForeignKey('material.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
)

# Tabela associativa para Favoritos de Materiais
material_favoritos = db.Table('material_favoritos',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('material_id', db.Integer, db.ForeignKey('material.id'), primary_key=True)
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
    topicos = db.relationship('Topico', backref='autor', lazy=True)
    respostas = db.relationship('Resposta', backref='autor', lazy=True)
    materiais = db.relationship('Material', backref='autor', lazy=True)
    eventos = db.relationship('Evento', backref='organizador', lazy=True)
    denuncias = db.relationship('Denuncia', backref='denunciante', lazy=True)
    relatos = db.relationship('RelatoSuporte', backref='relator', lazy=True)
    notificacoes = db.relationship('Notificacao', backref='usuario', lazy=True)
    
    # NOVA RELAÇÃO: Materiais favoritados pelo usuário
    materiais_favoritos_rel = db.relationship('Material', secondary=material_favoritos, backref=db.backref('favoritado_por', lazy='dynamic'))
    
    # NOVA RELAÇÃO: Comunidades que o usuário segue
    comunidades_seguidas = db.relationship('Comunidade', secondary=membros_comunidade, backref=db.backref('membros', lazy='dynamic'))
    
    # NOVA RELAÇÃO: Solicitações de entrada em grupos privados
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
    
    # Seus colegas usaram foto_perfil aqui? O User já tem foto_url. 
    # Vou manter o que estava no seu User original para garantir.
    # Se tiver conflito, avise.

    def __repr__(self):
        return f'<Perfil do usuário {self.user_id}>'


class Notificacao(db.Model):
    __tablename__ = 'notificacao'

    id = db.Column(db.Integer, primary_key=True)
    mensagem = db.Column(db.String(300), nullable=False)
    link_url = db.Column(db.String(300), nullable=True)
    lida = db.Column(db.Boolean, default=False)
    data_criacao = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    usuario_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f'<Notificação para {self.usuario_id}>'


# ===================================================================
# COMUNIDADES E SOLICITAÇÕES (NOVO)
# ===================================================================

class SolicitacaoParticipacao(db.Model):
    __tablename__ = 'solicitacao_participacao'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comunidade_id = db.Column(db.Integer, db.ForeignKey('comunidade.id'), nullable=False)
    data_solicitacao = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(20), default='Pendente') # Pendente, Aceito, Rejeitado


class Comunidade(db.Model):
    __tablename__ = 'comunidade'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)
    descricao = db.Column(db.String(300), nullable=False)
    
    # Novos campos para deixar "Profissional"
    categoria = db.Column(db.String(50), default='Geral') 
    tipo_acesso = db.Column(db.String(20), default='Público') # Público ou Restrito
    regras = db.Column(db.Text, nullable=True)
    
    imagem_url = db.Column(db.String(300), default='default_community.png')
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    criador_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relacionamentos
    topicos = db.relationship('Topico', backref='comunidade', lazy=True)
    moderadores = db.relationship('User', secondary=moderadores_comunidade, backref=db.backref('comunidades_moderadas', lazy='dynamic'))
    solicitacoes = db.relationship('SolicitacaoParticipacao', backref='comunidade', lazy=True)

    def __repr__(self):
        return f'<Comunidade {self.nome}>'


# ===================================================================
# FÓRUM (ATUALIZADO COM IMAGENS, HIERARQUIA E LIKES)
# ===================================================================

class Topico(db.Model):
    __tablename__ = 'topico'

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    conteudo = db.Column(db.Text, nullable=False)
    
    # CAMPO NOVO: Imagem no Post
    imagem_post = db.Column(db.String(300), nullable=True) 
    
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    autor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # CAMPO NOVO: Link com Comunidade
    comunidade_id = db.Column(db.Integer, db.ForeignKey('comunidade.id'), nullable=True)
    
    # Relacionamentos (Cascade para deletar tudo se o tópico for apagado)
    respostas = db.relationship('Resposta', backref='topico', lazy=True, cascade="all, delete-orphan")
    likes = db.relationship('PostLike', backref='topico', lazy=True, cascade="all, delete-orphan")
    salvos = db.relationship('PostSalvo', backref='topico', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Topico {self.titulo}>'


class Resposta(db.Model):
    __tablename__ = 'resposta'

    id = db.Column(db.Integer, primary_key=True)
    conteudo = db.Column(db.Text, nullable=False)
    
    # CAMPO NOVO: Imagem no Comentário
    imagem_resposta = db.Column(db.String(300), nullable=True)
    
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    topico_id = db.Column(db.Integer, db.ForeignKey('topico.id'), nullable=False)
    autor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # --- O SEGREDO DA ESCADINHA (HIERARQUIA) ---
    parent_id = db.Column(db.Integer, db.ForeignKey('resposta.id'), nullable=True)
    
    filhos = db.relationship('Resposta', 
                             backref=db.backref('pai', remote_side=[id]), 
                             lazy=True, 
                             cascade="all, delete-orphan")

    # NOVO: Likes nos comentários
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

    def __repr__(self):
        return f'<Like do User {self.user_id} no Tópico {self.topico_id}>'


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

    def __repr__(self):
        return f'<Post Salvo do User {self.user_id} (Tópico {self.topico_id})>'


# ===================================================================
# MAPA E EVENTOS (MANTIDOS DO ORIGINAL)
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

    def __repr__(self):
        return f'<Ponto {self.nome}>'


class Evento(db.Model):
    __tablename__ = 'evento'

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    data_hora_inicio = db.Column(db.DateTime, nullable=False)
    local_id = db.Column(db.Integer, db.ForeignKey('ponto_de_interesse.id'), nullable=True)
    organizador_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    def __repr__(self):
        return f'<Evento {self.titulo}>'


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
# MATERIAIS (MANTIDOS DO ORIGINAL)
# ===================================================================

class Material(db.Model):
    __tablename__ = 'material'

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    arquivo_path = db.Column(db.String(300), nullable=True)
    link_externo = db.Column(db.String(500), nullable=True) # Link externo (YouTube, Drive, etc.)
    
    # NOVOS CAMPOS
    imagem_capa = db.Column(db.String(300), nullable=True) # Caminho da imagem de capa
    download_count = db.Column(db.Integer, default=0)      # Contador de downloads
    
    data_upload = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    categoria = db.Column(db.String(100), nullable=True)
    autor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # Relacionamento com Tags
    tags = db.relationship('Tag', secondary=material_tags, backref=db.backref('materiais', lazy='dynamic'))

    def __repr__(self):
        return f'<Material {self.titulo}>'


class Tag(db.Model):
    __tablename__ = 'tag'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), unique=True, nullable=False)
    
    def __repr__(self):
        return f'<Tag {self.nome}>'


# ===================================================================
# SUPORTE (MANTIDOS DO ORIGINAL)
# ===================================================================

class RelatoSuporte(db.Model):
    __tablename__ = 'relato_suporte'

    id = db.Column(db.Integer, primary_key=True)
    tipo_relato = db.Column(db.String(50), nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    data_envio = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(50), default='Recebido')
    relator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    def __repr__(self):
        return f'<Relato de Suporte #{self.id}>'


class FAQ(db.Model):
    __tablename__ = 'faq'

    id = db.Column(db.Integer, primary_key=True)
    pergunta = db.Column(db.String(255), nullable=False)
    resposta = db.Column(db.Text, nullable=False)
    categoria = db.Column(db.String(50), nullable=True)

    def __repr__(self):
        return f'<FAQ: {self.pergunta[:30]}>'


# ===================================================================
# DENÚNCIAS (MANTIDOS DO ORIGINAL)
# ===================================================================

class Denuncia(db.Model):
    __tablename__ = 'denuncia'

    id = db.Column(db.Integer, primary_key=True)
    tipo_denuncia = db.Column(db.String(50), nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    data_envio = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(50), default='Recebida')
    denunciante_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    def __repr__(self):
        return f'<Denúncia #{self.id}>'
