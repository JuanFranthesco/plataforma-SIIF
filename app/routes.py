from flask import render_template, request, redirect, url_for, flash, current_app, send_from_directory, Blueprint, session
import requests
from flask_login import login_required, current_user
from sqlalchemy import or_, desc, func, text        
from werkzeug.utils import secure_filename
import os
import datetime
import secrets
from PIL import Image
from thefuzz import fuzz
import bleach
from unidecode import unidecode  # <--- IMPORTANTE: Adicione isso
from .lista_proibida import PALAVRAS_GLOBAIS
import json
# app/routes.py (Topo do arquivo)



# --- CONFIGURAÇÕES DE SEGURANÇA E CONSTANTES ---
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'jpg', 'jpeg', 'png', 'mp4'}

CATEGORIAS_PADRAO = [
    "Artes", "Biologia", "Educação Física", "Filosofia", "Física", "Geografia", "História",
    "Língua Estrangeira", "Língua Portuguesa", "Matemática", "Química", "Sociologia",
    "Informática", "Redes de Computadores", "Análise e Desenv. de Sistemas", "Engenharia de Computação",
    "Edificações", "Eletrotécnica", "Mecânica", "Petróleo e Gás", "Saneamento", "Segurança do Trabalho",
    "Agroecologia", "Agropecuária", "Zootecnia", "Meio Ambiente", "Gestão Ambiental",
    "Administração", "Logística", "Eventos", "Turismo",
    "TCC/Monografias", "Documentos Institucionais", "Geral"
]


def allowed_file(filename: str) -> bool:
    """Verifica se a extensão do arquivo é permitida."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def sanitize_input(text: str) -> str:
    """Remove tags HTML potencialmente perigosas de texto de entrada."""
    if not text:
        return ""
    return bleach.clean(text, tags=[], strip=True)



# Imports completos dos modelos (Incluindo as novas tabelas)
from app.models import (
    Material, User, FAQ, Denuncia, Noticia, Evento, Perfil,
    Topico, Resposta, PostSalvo, PostLike, Notificacao,
    Comunidade, SolicitacaoParticipacao, RespostaLike, Tag, ComunidadeTag, AuditLog,
    EnqueteOpcao, EnqueteVoto, RelatoSuporte, KanbanTask
)

# app/routes.py (Topo)
from app.models import (
    # ... outros modelos ...
    Tag, ComunidadeTag, AuditLog,
    EnqueteOpcao, EnqueteVoto  # <--- ADICIONE AQUI
)

from app.extensions import db, limiter
from app.forms import ProfileForm
from app.auth import get_suap_session

main_bp = Blueprint('main', __name__)


@main_bp.after_request
def add_header(response):
    """
    Adiciona cabeçalhos para evitar cache em rotas protegidas.
    """
    response.headers["Cache-Control"] = "no-cache, private, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Vary"] = "Cookie"

    # Remove ETag and Last-Modified to prevent conditional requests (HTTP 304)
    if 'ETag' in response.headers:
        del response.headers['ETag']
    if 'Last-Modified' in response.headers:
        del response.headers['Last-Modified']

    return response


@main_bp.app_errorhandler(413)
def request_entity_too_large(error):
    flash('O arquivo enviado é muito grande. O limite é 16MB.', 'danger')
    return redirect(request.url)


# --- FILTRO DE DATA (Para mostrar '21/11 às 14:30' no HTML) ---
@main_bp.app_template_filter('format_data_br')
def format_data_br(dt):
    if dt is None:
        return ""
    # Converte UTC para Horário de Brasília (UTC-3)
    dt_brasil = dt - datetime.timedelta(hours=3)
    return dt_brasil.strftime('%d/%m às %H:%M')


# --- FUNÇÕES AUXILIARES ---
def registrar_log(comunidade_id, acao, detalhes=None):
    """Salva uma ação no histórico da comunidade."""
    log = AuditLog(acao=acao, detalhes=detalhes, comunidade_id=comunidade_id, autor_id=current_user.id)
    db.session.add(log)
    db.session.commit()

def verificar_automod(texto: str, comunidade=None) -> bool:
    """
    Retorna True se o texto contiver palavras proibidas.
    Usa unidecode para ignorar acentos (ex: detecta 'cocô' se 'coco' estiver na lista).
    """
    if not texto: return False
    
    
    texto_limpo = unidecode(texto.lower())
    
    # 1. VERIFICAÇÃO GLOBAL (Obrigatória)
    for palavra in PALAVRAS_GLOBAIS:
        # Normaliza a palavra proibida também, por segurança
        palavra_limpa = unidecode(palavra.lower())
        
    
        if palavra_limpa in texto_limpo:
            return True

    # 2. VERIFICAÇÃO DA COMUNIDADE
    if comunidade and comunidade.palavras_proibidas:
        proibidas_comunidade = [p.strip() for p in comunidade.palavras_proibidas.split(',') if p.strip()]
        
        for palavra in proibidas_comunidade:
            palavra_limpa_comm = unidecode(palavra.lower())
            if palavra_limpa_comm in texto_limpo:
                return True
                
    return False
# ===================================================================
# TELA INICIAL E REDIRECIONAMENTOS
# ===================================================================

@main_bp.route('/')
@main_bp.route('/index')
def index():
    return redirect(url_for('main.tela_inicial'))


@main_bp.route('/home')
@main_bp.route('/tela-inicial')
@login_required
def tela_inicial():
    """
    Tela inicial com dados reais do banco:
    - Últimas notícias (FILTRADAS POR CAMPUS)
    - Próximos eventos
    """
    # Se for admin, redireciona para o painel dele
    if current_user.is_admin:
        return redirect(url_for('main.tela_admin'))

    # --- LÓGICA DE FILTRO POR CAMPUS (CORRIGIDA) ---
    query_noticias = Noticia.query

    # Verifica se o usuário tem campus definido (vem do SUAP)
    if current_user.campus:
        termo_campus = current_user.campus

        # Filtra: Notícias do campus do usuário OU notícias Gerais/IFRN
        query_noticias = query_noticias.filter(
            or_(
                Noticia.campus.ilike(f'%{termo_campus}%'),
                Noticia.campus.in_(['IFRN', 'Geral', 'Todos'])
            )
        )

    # Ordena por data e pega as 4 mais recentes
    noticias = query_noticias.order_by(Noticia.data_postagem.desc()).limit(4).all()

    # --- LÓGICA DE EVENTOS (EVENTOS FUTUROS) ---
    agora = datetime.datetime.now(datetime.timezone.utc)

    eventos = (
        Evento.query
        .filter(Evento.data_hora_inicio >= agora)
        .order_by(Evento.data_hora_inicio.asc())
        .limit(4)
        .all()
    )

    return render_template(
        'tela_inicial.html',
        noticias=noticias,
        eventos=eventos
    )


# ===================================================================
# COMUNIDADES (NOVA FUNCIONALIDADE)
# ===================================================================

@main_bp.route('/comunidades')
@login_required
def tela_comunidades():
    busca = request.args.get('q')
    categoria_filtro = request.args.get('categoria')
    
    query = Comunidade.query

    if busca:
        query = query.filter(Comunidade.nome.ilike(f'%{busca}%'))
    
    if categoria_filtro and categoria_filtro != 'Todas':
        query = query.filter(Comunidade.categoria == categoria_filtro)

    comunidades = query.order_by(Comunidade.nome).all()
    
    categorias_db = db.session.query(Comunidade.categoria).distinct().order_by(Comunidade.categoria).all()
    categorias = [c[0] for c in categorias_db if c[0]]

    return render_template(
        'tela_comunidades.html', 
        comunidades=comunidades, 
        busca=busca, 
        categorias=categorias, 
        categoria_atual=categoria_filtro
    )


@main_bp.route('/comunidades/criar', methods=['POST'])
@login_required
def criar_comunidade():
    try:
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        categoria = request.form.get('categoria')
        tipo = request.form.get('tipo')
        imagem = request.files.get('imagem')
        
        if not nome or not descricao:
            flash('Preencha todos os campos.', 'warning')
            return redirect(url_for('main.tela_comunidades'))
            
        if Comunidade.query.filter(func.lower(Comunidade.nome) == func.lower(nome)).first():
            flash('Nome já existe.', 'danger')
            return redirect(url_for('main.tela_comunidades'))

        nova_com = Comunidade(
            nome=nome,
            descricao=descricao,
            categoria=categoria,
            tipo_acesso=tipo,
            criador_id=current_user.id
        )
        
        if imagem and imagem.filename:
            filename = secure_filename(imagem.filename)
            ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            fname = f"com_{ts}_{filename}"
            path = os.path.join(current_app.config['UPLOAD_FOLDER'], fname)
            imagem.save(path)
            nova_com.imagem_url = f"/static/uploads/{fname}"
        
        nova_com.membros.append(current_user)
        nova_com.moderadores.append(current_user)
        
        db.session.add(nova_com)
        db.session.commit()
        
        flash('Comunidade criada!', 'success')
        return redirect(url_for('main.ver_comunidade', comunidade_id=nova_com.id))

    except Exception as e:
        db.session.rollback()
        flash(f'Erro: {e}', 'danger')
        return redirect(url_for('main.tela_comunidades'))


@main_bp.route('/comunidade/<int:comunidade_id>/participar')
@login_required
def participar_comunidade(comunidade_id):
    comunidade = Comunidade.query.get_or_404(comunidade_id)
    
    if current_user in comunidade.membros:
        comunidade.membros.remove(current_user)
        if current_user in comunidade.moderadores and comunidade.criador_id != current_user.id:
            comunidade.moderadores.remove(current_user)
        
        flash(f'Saiu de {comunidade.nome}.', 'info')
        db.session.commit()
        return redirect(request.referrer)

    if comunidade.tipo_acesso == 'Restrito':
        solicitacao = SolicitacaoParticipacao.query.filter_by(user_id=current_user.id, comunidade_id=comunidade.id).first()
        if solicitacao:
            flash('Aguarde aprovação.', 'warning')
        else:
            db.session.add(SolicitacaoParticipacao(user_id=current_user.id, comunidade_id=comunidade.id))
            db.session.commit()
            flash('Solicitação enviada.', 'success')
    else:
        comunidade.membros.append(current_user)
        db.session.commit()
        flash(f'Entrou em {comunidade.nome}!', 'success')
        
    return redirect(request.referrer)


@main_bp.route('/c/<int:comunidade_id>')
@login_required
def ver_comunidade(comunidade_id):
    comunidade = Comunidade.query.get_or_404(comunidade_id)
    
    # Filtro vindo da URL (ex: ?tipo=material)
    filtro_tipo = request.args.get('tipo')
    
    tem_acesso = True
    if comunidade.tipo_acesso == 'Restrito' and current_user not in comunidade.membros:
        tem_acesso = False
        topicos = []
    else:
        # Query Base
        query = Topico.query.filter_by(comunidade_id=comunidade.id)
        
        # Aplica Filtros
        if filtro_tipo == 'enquete':
            query = query.filter(Topico.tipo_post == 'enquete')
        elif filtro_tipo == 'material':
            # Pega tipo 'material' OU posts que tenham anexo de material
            query = query.filter(or_(Topico.tipo_post == 'material', Topico.material_id != None))
        elif filtro_tipo == 'midia':
            # Pega posts com imagem/video ou tipo 'geral' com imagem
            query = query.filter(Topico.imagem_post != None)
            
        # Ordenação: FIXADOS PRIMEIRO, depois os mais recentes
        topicos = query.order_by(desc(Topico.fixado), desc(Topico.criado_em)).all()
    
    # ... (O RESTO DA FUNÇÃO CONTINUA IGUAL: likes, salvos, etc...)
    likes_usuario = [l.topico_id for l in PostLike.query.filter_by(user_id=current_user.id).all()]
    salvos_usuario = [s.topico_id for s in PostSalvo.query.filter_by(user_id=current_user.id).all()]
    likes_respostas_usuario = [l.resposta_id for l in RespostaLike.query.filter_by(user_id=current_user.id).all()]
    
    votos_usuario = []
    if tem_acesso:
        ids_opcoes_votadas = db.session.query(EnqueteVoto.opcao_id).filter(EnqueteVoto.user_id == current_user.id).all()
        votos_usuario = [v[0] for v in ids_opcoes_votadas]

    solicitacao_pendente = False
    if not tem_acesso:
        if SolicitacaoParticipacao.query.filter_by(user_id=current_user.id, comunidade_id=comunidade.id).first():
            solicitacao_pendente = True

    sugestoes = Comunidade.query.filter(Comunidade.id != comunidade.id).limit(3).all()
    recent_noticias = Noticia.query.order_by(desc(Noticia.data_postagem)).limit(10).all()
    recent_materiais = Material.query.order_by(desc(Material.data_upload)).limit(10).all()

    return render_template('tela_comunidade_detalhe.html', 
        comunidade=comunidade, topicos=topicos, likes_usuario=likes_usuario, 
        salvos_usuario=salvos_usuario, likes_respostas_usuario=likes_respostas_usuario, 
        tem_acesso=tem_acesso, solicitacao_pendente=solicitacao_pendente, 
        sugestoes=sugestoes, votos_usuario=votos_usuario, 
        lista_noticias=recent_noticias, lista_materiais=recent_materiais,
        filtro_atual=filtro_tipo # Passamos o filtro para o template saber qual botão pintar
    )

    

# ===================================================================
# GESTÃO E MODERAÇÃO (DASHBOARD)
# ===================================================================

@main_bp.route('/c/<int:comunidade_id>/configurar', methods=['GET', 'POST'])
@login_required
def configurar_comunidade(comunidade_id):
    comunidade = Comunidade.query.get_or_404(comunidade_id)
    
    # 1. Verificação de Permissões (Dono, Mod ou Admin)
    eh_dono = (comunidade.criador_id == current_user.id)
    eh_mod = (current_user in comunidade.moderadores)
    
    if not eh_dono and not eh_mod and not current_user.is_admin:
        flash('Você não tem permissão para configurar esta comunidade.', 'danger')
        return redirect(url_for('main.ver_comunidade', comunidade_id=comunidade.id))

    if request.method == 'POST':
        
        # --- CENÁRIO A: FORMULÁRIO GERAL (Visual, Regras, Links) ---
        # Verificamos se o campo 'descricao' existe para saber se veio da aba Geral
        if 'descricao' in request.form:
            comunidade.descricao = request.form.get('descricao')
            comunidade.regras = request.form.get('regras')
            comunidade.cor_tema = request.form.get('cor_tema')
            comunidade.mensagem_boas_vindas = request.form.get('mensagem_boas_vindas') # Novo campo

            # Upload de Imagens (Logo e Banner)
            imagem = request.files.get('imagem_comunidade')
            banner = request.files.get('banner_comunidade')
            ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S") # Timestamp para evitar cache

            if imagem and imagem.filename:
                fname = secure_filename(imagem.filename)
                # Salva no disco
                path = os.path.join(current_app.config['UPLOAD_FOLDER'], f"logo_{ts}_{fname}")
                imagem.save(path)
                # Salva caminho no banco
                comunidade.imagem_url = f"/static/uploads/logo_{ts}_{fname}"
                
            if banner and banner.filename:
                fname = secure_filename(banner.filename)
                path = os.path.join(current_app.config['UPLOAD_FOLDER'], f"banner_{ts}_{fname}")
                banner.save(path)
                comunidade.banner_url = f"/static/uploads/banner_{ts}_{fname}"

            # --- [NOVO] SALVAR LINKS ÚTEIS (JSON) ---
            nomes = request.form.getlist('link_nome[]')
            urls = request.form.getlist('link_url[]')
            
            novos_links = []
            for nome, url in zip(nomes, urls):
                if nome.strip() and url.strip(): # Só salva se tiver texto
                    novos_links.append({'nome': nome.strip(), 'url': url.strip()})
            
            # Converte lista para texto JSON ou define como None se vazio
            comunidade.links_uteis = json.dumps(novos_links) if novos_links else None
            
            registrar_log(comunidade.id, "Atualizou identidade visual e links")
            flash('Configurações visuais salvas!', 'success')

        # --- CENÁRIO B: FORMULÁRIO DE SEGURANÇA ---
        # Verificamos se 'palavras_proibidas' existe para saber se veio da aba Segurança
        elif 'palavras_proibidas' in request.form:
            comunidade.palavras_proibidas = request.form.get('palavras_proibidas')
            
            # Checkbox HTML não envia nada se desmarcado, então verificamos presença
            comunidade.trancada = 'trancada' in request.form
            
            if 'tipo_acesso' in request.form:
                comunidade.tipo_acesso = request.form.get('tipo_acesso')

            registrar_log(comunidade.id, "Atualizou configurações de segurança")
            flash('Configurações de segurança salvas!', 'success')

        # Commit final no banco
        db.session.commit()
        return redirect(url_for('main.configurar_comunidade', comunidade_id=comunidade.id))
    
    # --- GET: Carregar dados para o Template ---
    solicitacoes = []
    if comunidade.tipo_acesso == 'Restrito':
        solicitacoes = SolicitacaoParticipacao.query.filter_by(comunidade_id=comunidade.id).all()
        
    tags = ComunidadeTag.query.filter_by(comunidade_id=comunidade.id).all()
    logs = AuditLog.query.filter_by(comunidade_id=comunidade.id).order_by(desc(AuditLog.data)).limit(20).all()
    
    stats = {
        'membros': comunidade.membros.count(),
        'posts': len(comunidade.topicos)
    }

    return render_template('tela_comunidade_config.html', 
                           comunidade=comunidade, 
                           solicitacoes=solicitacoes,
                           tags=tags, 
                           logs=logs,
                           stats=stats)


@main_bp.route('/c/<int:comunidade_id>/tags/criar', methods=['POST'])
@login_required
def criar_tag(comunidade_id):
    comunidade = Comunidade.query.get_or_404(comunidade_id)
    if current_user not in comunidade.moderadores: return redirect(request.referrer)
    
    nome = request.form.get('nome_tag')
    cor = request.form.get('cor_tag')
    if nome:
        db.session.add(ComunidadeTag(nome=nome, cor=cor, comunidade_id=comunidade.id))
        registrar_log(comunidade.id, f"Criou tag: {nome}")
        db.session.commit()
    return redirect(url_for('main.configurar_comunidade', comunidade_id=comunidade.id))


@main_bp.route('/c/<int:comunidade_id>/tags/<int:tag_id>/excluir')
@login_required
def excluir_tag(comunidade_id, tag_id):
    tag = ComunidadeTag.query.get_or_404(tag_id)
    if current_user in tag.comunidade.moderadores:
        db.session.delete(tag)
        db.session.commit()
    return redirect(url_for('main.configurar_comunidade', comunidade_id=comunidade_id))


@main_bp.route('/c/<int:comunidade_id>/promover/<int:user_id>')
@login_required
def promover_moderador(comunidade_id, user_id):
    comunidade = Comunidade.query.get_or_404(comunidade_id)
    alvo = User.query.get_or_404(user_id)
    
    if comunidade.criador_id != current_user.id and not current_user.is_admin:
        flash('Apenas o dono pode gerenciar moderadores.', 'danger')
        return redirect(url_for('main.configurar_comunidade', comunidade_id=comunidade_id))
        
    if alvo not in comunidade.moderadores:
        comunidade.moderadores.append(alvo)
        registrar_log(comunidade.id, f"Promoveu {alvo.name}")
        flash(f'{alvo.name} agora é moderador!', 'success')
    else:
        comunidade.moderadores.remove(alvo)
        registrar_log(comunidade.id, f"Rebaixou {alvo.name}")
        flash(f'{alvo.name} não é mais moderador.', 'info')
        
    db.session.commit()
    return redirect(url_for('main.configurar_comunidade', comunidade_id=comunidade_id))


@main_bp.route('/c/<int:comunidade_id>/solicitacoes/<int:sol_id>/<acao>')
@login_required
def gerenciar_solicitacao(comunidade_id, sol_id, acao):
    comunidade = Comunidade.query.get_or_404(comunidade_id)
    
    if current_user not in comunidade.moderadores and not current_user.is_admin:
        return redirect(url_for('main.ver_comunidade', comunidade_id=comunidade_id))
        
    solicitacao = SolicitacaoParticipacao.query.get_or_404(sol_id)
    
    if acao == 'aceitar':
        usuario = User.query.get(solicitacao.user_id)
        comunidade.membros.append(usuario)
        registrar_log(comunidade.id, f"Aceitou {usuario.name}")
        db.session.delete(solicitacao)
        db.session.commit()
        flash(f'{usuario.name} aceito!', 'success')
    elif acao == 'recusar':
        db.session.delete(solicitacao)
        db.session.commit()
        flash('Solicitação recusada.', 'info')
        
    return redirect(url_for('main.configurar_comunidade', comunidade_id=comunidade_id))


# ===================================================================
# FÓRUM GERAL E POSTAGEM (ATUALIZADO)
# ===================================================================

@main_bp.route('/forum')
@login_required
def tela_foruns():
    termo_pesquisa = request.args.get('q')
    ordenar_por = request.args.get('ordenarPor')
    filtro = request.args.get('filtro')

    # Query Base: Tópicos + Join com Comunidade
    query = Topico.query.outerjoin(Comunidade)
    
    # --- FILTROS DE PRIVACIDADE E TIPO ---
    query = query.filter(
        # 1. Privacidade: Mostra posts Globais (sem comunidade) OU de Comunidades Públicas
        or_(
            Topico.comunidade_id == None,
            Comunidade.tipo_acesso != 'Restrito'
        )
    ).filter(
        # 2. Tipo: NÃO MOSTRAR Enquetes no feed global (Regra de Negócio)
        Topico.tipo_post != 'enquete'
    )

    # Filtros de Pesquisa
    if termo_pesquisa:
        query = query.filter(or_(
            Topico.titulo.ilike(f'%{termo_pesquisa}%'),
            Topico.conteudo.ilike(f'%{termo_pesquisa}%')
        ))

    # Filtro de Salvos
    if filtro == 'salvos':
        query = query.join(PostSalvo).filter(PostSalvo.user_id == current_user.id)

    # Ordenação
    if ordenar_por == 'relevancia':
        query = query.outerjoin(PostLike).group_by(Topico.id).order_by(desc(func.count(PostLike.id)))
    else:
        query = query.order_by(desc(Topico.criado_em))

    topicos = query.all()

    likes_usuario = [l.topico_id for l in PostLike.query.filter_by(user_id=current_user.id).all()]
    salvos_usuario = [s.topico_id for s in PostSalvo.query.filter_by(user_id=current_user.id).all()]
    
    # Carrega notificações
    notificacoes = Notificacao.query.filter_by(usuario_id=current_user.id, lida=False).order_by(desc(Notificacao.data_criacao)).limit(30).all()

    # Carrega comunidades do usuário para o modal de postagem
    comunidades = current_user.comunidades_seguidas

    # Passamos 'votos_usuario' vazio pois não mostramos enquetes aqui, evita erro no template se ele tentar ler
    return render_template(
        'tela_foruns.html',
        topicos=topicos,
        likes_usuario=likes_usuario,
        salvos_usuario=salvos_usuario,
        notificacoes=notificacoes,
        votos_usuario=[],
        comunidades=comunidades,
        filtro_selecionado=filtro
    )

@main_bp.route('/forum/notificacoes/mark_all_seen', methods=['POST'])
@login_required
def marcar_todas_notificacoes_lidas_forum():
    try:
        Notificacao.query.filter_by(usuario_id=current_user.id, lida=False).update({'lida': True})
        db.session.commit()
        flash('Todas as notificações foram marcadas como vistas.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao marcar notificações como vistas: {e}', 'danger')
    return redirect(request.referrer or url_for('main.tela_foruns'))


@main_bp.route('/forum/notificacoes/mark_all_seen', methods=['POST'])
@login_required
def marcar_todas_notificacoes_lidas():
    try:
        Notificacao.query.filter_by(usuario_id=current_user.id, lida=False).update({'lida': True})
        db.session.commit()
        flash('Todas as notificações foram marcadas como vistas.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao marcar notificações como vistas: {e}', 'danger')
    return redirect(url_for('main.tela_foruns'))


# app/routes.py (Função criar_post)

@main_bp.route('/forum/postar', methods=['POST'])
@login_required
def criar_post():
    comunidade_id = request.form.get('comunidade_id')
    if comunidade_id == '':
        comunidade_id = None
    tag_id = request.form.get('tag_id')
    tipo_selecionado = request.form.get('tipo_post_selecionado', 'geral') 
    
    titulo = ""
    conteudo = ""
    link_url = None
    noticia_id = None
    material_id = None
    imagem_path = None
    
    # 1. PEGAR DADOS DEPENDENDO DA ABA SELECIONADA
    if tipo_selecionado == 'enquete':
        titulo = request.form.get('titulo_enquete_fake', '').strip()
        conteudo = request.form.get('descricao_enquete', '')

    elif tipo_selecionado == 'link':
        link_url = request.form.get('link_url')
        conteudo = request.form.get('descricao_link', '')
        # Se o usuário não digitou título, usa a descrição ou um padrão
        input_titulo = request.form.get('descricao_link', '').strip()
        titulo = input_titulo if input_titulo else "Link Compartilhado"
        
        if not link_url:
            flash('Insira a URL.', 'danger')
            return redirect(request.referrer)

    elif tipo_selecionado == 'noticia':
        noticia_id = request.form.get('noticia_selecionada')
        if noticia_id:
            n = Noticia.query.get(noticia_id)
            if n: titulo = f"Compartilhou: {n.titulo}"

    elif tipo_selecionado == 'material':
        material_id = request.form.get('material_selecionado')
        if material_id:
            m = Material.query.get(material_id)
            if m: titulo = f"Compartilhou: {m.titulo}"

    else: # Caso 'geral' ou 'media'
        titulo = request.form.get('titulo_post', '').strip()
        conteudo = request.form.get('conteudo_post', '')
        imagem = request.files.get('midia_post')
        
        if imagem and imagem.filename:
            fname = secure_filename(imagem.filename)
            ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            filename = f"post_{ts}_{fname}"
            path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            imagem.save(path)
            imagem_path = f"/static/uploads/{filename}"
            # Se tem imagem mas não tem título
            if not titulo: titulo = "Compartilhou uma mídia"

    # Fallback final
    if not titulo:
        titulo = "Nova Publicação"

    # ==================================================================
    # [BLOQUEIO DE SEGURANÇA] VERIFICAÇÃO DE PALAVRAS PROIBIDAS
    # ==================================================================
    # Busca a comunidade se houver (para aplicar regras locais + globais)
    comunidade_alvo = None
    if comunidade_id:
        comunidade_alvo = Comunidade.query.get(comunidade_id)

    # Junta título e conteúdo para verificar tudo de uma vez
    texto_para_analise = f"{titulo} {conteudo}"

    # Chama a função verificadora (Global + Comunidade)
    if verificar_automod(texto_para_analise, comunidade_alvo):
        flash('🚫 Postagem bloqueada: O texto contém palavras ofensivas ou proibidas nesta comunidade.', 'danger')
        return redirect(request.referrer)
    # ==================================================================

    # 3. SALVAR NO BANCO (Só chega aqui se o AutoMod permitir)
    novo_topico = Topico(
        titulo=titulo,
        conteudo=conteudo,
        tipo_post=tipo_selecionado,
        imagem_post=imagem_path,
        link_url=link_url,
        noticia_id=noticia_id,
        material_id=material_id,
        autor_id=current_user.id,
        comunidade_id=comunidade_id,
        tag_id=tag_id if tag_id else None
    )

    db.session.add(novo_topico)
    db.session.commit()

    # 4. SALVAR OPÇÕES DA ENQUETE (Se for enquete)
    if tipo_selecionado == 'enquete':
        opcoes_texto = request.form.getlist('opcao_enquete[]')
        for texto_opt in opcoes_texto:
            if texto_opt.strip():
                # Verifica também se as opções da enquete têm palavrão
                if verificar_automod(texto_opt, comunidade_alvo):
                    # Se tiver, apaga o tópico recém criado e avisa
                    db.session.delete(novo_topico)
                    db.session.commit()
                    flash('🚫 Postagem bloqueada: Uma das opções da enquete contém palavras proibidas.', 'danger')
                    return redirect(request.referrer)
                
                nova_opcao = EnqueteOpcao(texto=texto_opt.strip(), topico_id=novo_topico.id)
                db.session.add(nova_opcao)
        db.session.commit()

    flash('Publicação criada com sucesso!', 'success')
    if comunidade_id:
        return redirect(url_for('main.ver_comunidade', comunidade_id=comunidade_id))
    else:
        return redirect(url_for('main.tela_foruns'))

@main_bp.route('/forum/<int:topico_id>/comentar', methods=['POST'])
@login_required
def comentar_post(topico_id):
    """
    Cria um comentário (COM UPLOAD, ANINHAMENTO E VERIFICAÇÃO DE AUTOMOD).
    """
    conteudo = request.form.get('conteudo_comentario')
    imagem = request.files.get('midia_comentario')
    parent_id = request.form.get('parent_id')  # ID do Pai

    topico = Topico.query.get_or_404(topico_id)

    # ==================================================================
    # [BLOQUEIO DE SEGURANÇA] VERIFICAÇÃO DE PALAVRAS PROIBIDAS
    # ==================================================================
    # Identifica a comunidade do tópico (se houver) para aplicar as regras dela
    comunidade_alvo = topico.comunidade if topico.comunidade else None

    # Verifica o conteúdo do comentário
    if verificar_automod(conteudo, comunidade_alvo):
        flash('🚫 Comentário bloqueado: O texto contém palavras ofensivas ou proibidas.', 'danger')
        return redirect(request.referrer)
    # ==================================================================

    if not conteudo and not imagem:
        flash('O comentário não pode ficar vazio.', 'warning')
        return redirect(request.referrer)

    pid = int(parent_id) if parent_id else None

    nova_resposta = Resposta(
        conteudo=conteudo if conteudo else "",
        topico_id=topico.id,
        autor_id=current_user.id,
        parent_id=pid  # Salva o aninhamento
    )

    # Salvar imagem do comentário
    if imagem and imagem.filename:
        filename = secure_filename(imagem.filename)
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"resp_{ts}_{filename}"
        path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)

        try:
            imagem.save(path)
            nova_resposta.imagem_resposta = f"/static/uploads/{filename}"
        except Exception as e:
            flash(f'Erro ao salvar imagem: {e}', 'danger')

    db.session.add(nova_resposta)

    # Notificação (Versão Otimizada)
    try:
        link_destino = url_for('main.ver_comunidade', comunidade_id=topico.comunidade_id) if topico.comunidade_id else url_for('main.tela_foruns')

        # Se for resposta a um comentário
        if pid:
            comentario_pai = Resposta.query.get(pid)
            if comentario_pai and comentario_pai.autor_id != current_user.id:
                db.session.add(Notificacao(
                    mensagem=f"{current_user.name} respondeu seu comentário.",
                    link_url=link_destino,
                    usuario_id=comentario_pai.autor_id
                ))

        # Se for comentário no post (apenas avisa o dono do post)
        elif topico.autor_id != current_user.id:
            db.session.add(Notificacao(
                mensagem=f"{current_user.name} comentou no seu post.",
                link_url=link_destino,
                usuario_id=topico.autor_id
            ))

        db.session.commit()
        flash('Comentário enviado!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao salvar comentário: {e}', 'danger')

    return redirect(request.referrer)


@main_bp.route('/comentario/<int:resposta_id>/like', methods=['POST'])
@login_required
def like_comentario(resposta_id):
    """
    Curte/Descurte um comentário.
    """
    resposta = Resposta.query.get_or_404(resposta_id)
    like = RespostaLike.query.filter_by(user_id=current_user.id, resposta_id=resposta.id).first()

    if like:
        db.session.delete(like)
    else:
        db.session.add(RespostaLike(user_id=current_user.id, resposta_id=resposta.id))

    db.session.commit()
    return redirect(request.referrer)


@main_bp.route('/forum/<int:topico_id>/like', methods=['POST'])
@login_required
def like_post(topico_id):
    topico = Topico.query.get_or_404(topico_id)
    like_existente = PostLike.query.filter_by(user_id=current_user.id, topico_id=topico.id).first()

    if like_existente:
        db.session.delete(like_existente)
    else:
        novo_like = PostLike(user_id=current_user.id, topico_id=topico.id)
        db.session.add(novo_like)

    db.session.commit()
    return redirect(request.referrer)


@main_bp.route('/forum/<int:topico_id>/salvar', methods=['POST'])
@login_required
def salvar_post(topico_id):
    topico = Topico.query.get_or_404(topico_id)
    save_existente = PostSalvo.query.filter_by(user_id=current_user.id, topico_id=topico.id).first()

    if save_existente:
        db.session.delete(save_existente)
        flash('Removido dos salvos.', 'info')
    else:
        novo_salvo = PostSalvo(user_id=current_user.id, topico_id=topico.id)
        db.session.add(novo_salvo)
        flash('Post salvo com sucesso!', 'success')

    db.session.commit()
    return redirect(request.referrer)


@main_bp.route('/forum/<int:topico_id>/excluir', methods=['POST'])
@login_required
def excluir_post(topico_id):
    topico = Topico.query.get_or_404(topico_id)

    # Permissão: Admin, Dono do Post ou Moderador da Comunidade
    eh_mod = topico.comunidade_id and (current_user in topico.comunidade.moderadores)

    if not current_user.is_admin and topico.autor_id != current_user.id and not eh_mod:
        flash('Você não tem permissão para fazer isso.', 'danger')
        return redirect(request.referrer)

    db.session.delete(topico)
    db.session.commit()

    flash('Tópico excluído.', 'warning')
    return redirect(request.referrer)


@main_bp.route('/forum/<int:topico_id>/denunciar', methods=['POST'])
@login_required
def denunciar_post(topico_id):
    topico = Topico.query.get_or_404(topico_id)
    descricao_denuncia = request.form.get('descricao')

    if not descricao_denuncia:
        flash('Você precisa fornecer um motivo.', 'danger')
        return redirect(request.referrer)

    descricao_completa = f"Denúncia Tópico #{topico.id} (Título: {topico.titulo})\nAutor: {topico.autor.name}\nMotivo: {descricao_denuncia}"

    nova_denuncia = Denuncia(
        tipo_denuncia="Denúncia de Post no Fórum",
        descricao=descricao_completa,
        denunciante_id=current_user.id
    )

    try:
        db.session.add(nova_denuncia)
        db.session.commit()
        flash('Denúncia enviada com sucesso.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao enviar denúncia: {e}', 'danger')

    return redirect(request.referrer)


# ===================================================================
# ROTAS SECUNDÁRIAS (MANTIDAS DO ORIGINAL)
# ===================================================================

@main_bp.route('/divulgacao')
@login_required
def tela_divulgacao():
    return render_template('tela_divulgacao.html')


@main_bp.route('/ferramentas')
@login_required
def tela_ferramentas():
    return render_template('tela_ferramentas.html')

def salvar_imagem_perfil(imagem_enviada):
    """Salva a imagem com código aleatório e retorna o nome do arquivo."""
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(imagem_enviada.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(current_app.root_path, 'static/fotos_perfil', picture_fn)

    # Redimensionar (opcional, mas bom para performance)
    output_size = (300, 300) # Você pode ajustar ou remover isso para o banner
    i = Image.open(imagem_enviada)
    # Se for banner, talvez não queira redimensionar tanto ou fazer crop diferente
    # i.thumbnail(output_size) 
    
    i.save(picture_path)
    return picture_fn

def deletar_imagem_antiga(nome_arquivo):
    """Remove o arquivo físico antigo, se não for o padrão."""
    # Lista de arquivos que NUNCA devem ser apagados
    imagens_padrao = ['default_profile.png', 'default_banner.jpg', 'default.png']
    
    if nome_arquivo and nome_arquivo not in imagens_padrao:
        caminho_arquivo = os.path.join(current_app.root_path, 'static/fotos_perfil', nome_arquivo)
        if os.path.exists(caminho_arquivo):
            try:
                os.remove(caminho_arquivo)
            except Exception as e:
                print(f"Erro ao excluir imagem antiga: {e}")

@main_bp.route('/ferramentas/abnt')
@login_required
def tela_abnt():
    return render_template('tela_abnt.html')

# 3. Rota específica para o Mapa (Reativando a rota antiga)
@main_bp.route('/mapa')
@login_required
def tela_mapa():
    return render_template('tela_mapa.html')

@main_bp.route('/ferramentas/esquema')
@login_required
def tela_esquematizador():
    return render_template('tela_esquematizador.html')

# Rota específica para o Kanban
@main_bp.route('/ferramentas/kanban')
@login_required
def tela_kanban():
    # Busca apenas as tarefas do usuário logado
    tasks = KanbanTask.query.filter_by(user_id=current_user.id).all()
    
    # Separa as tarefas por status para enviar fácil para o HTML
    todo = [t for t in tasks if t.status == 'todo']
    doing = [t for t in tasks if t.status == 'doing']
    done = [t for t in tasks if t.status == 'done']
    
    return render_template('tela_kanban.html', todo=todo, doing=doing, done=done)

# --- API: ADICIONAR TAREFA ---
@main_bp.route('/api/kanban/add', methods=['POST'])
@login_required
def api_add_task():
    data = request.json
    
    # Converte string de data para objeto date (se existir)
    prazo_val = None
    if data.get('prazo'):
        try:
            prazo_val = datetime.datetime.strptime(data.get('prazo'), '%Y-%m-%d').date()
        except:
            pass

    nova_task = KanbanTask(
        titulo=data.get('titulo'),
        detalhes=data.get('detalhes'),
        status='todo', # Sempre começa em 'A Fazer'
        prazo=prazo_val,
        user_id=current_user.id
    )
        
    db.session.add(nova_task)
    db.session.commit()
    return jsonify(nova_task.to_dict())

# --- API: MOVER TAREFA (Drag & Drop) ---
@main_bp.route('/api/kanban/move/<int:task_id>', methods=['POST'])
@login_required
def api_move_task(task_id):
    task = KanbanTask.query.get_or_404(task_id)
    
    # Segurança: garante que a tarefa é do usuário logado
    if task.user_id != current_user.id:
        return jsonify({'erro': 'Acesso negado'}), 403
        
    novo_status = request.json.get('status')
    if novo_status in ['todo', 'doing', 'done']:
        task.status = novo_status
        db.session.commit()
        return jsonify({'msg': 'Movido com sucesso'})
    return jsonify({'erro': 'Status inválido'}), 400

# --- API: DELETAR TAREFA ---
@main_bp.route('/api/kanban/delete/<int:task_id>', methods=['DELETE'])
@login_required
def api_delete_task(task_id):
    task = KanbanTask.query.get_or_404(task_id)
    if task.user_id != current_user.id:
        return jsonify({'erro': 'Acesso negado'}), 403
        
    db.session.delete(task)
    db.session.commit()
    return jsonify({'msg': 'Deletado'})

# --- API: LIMPAR CONCLUÍDAS ---
@main_bp.route('/api/kanban/clear_done', methods=['POST'])
@login_required
def api_clear_done():
    # Deleta todas as tarefas 'done' deste usuário
    KanbanTask.query.filter_by(user_id=current_user.id, status='done').delete()
    db.session.commit()
    return jsonify({'msg': 'Limpeza concluída'})

@main_bp.route('/perfil', methods=['GET', 'POST'])
@login_required
def tela_perfil():
    # Agora o formulário é preenchido diretamente com o USUÁRIO
    form = ProfileForm(obj=current_user)

    if form.validate_on_submit():
        if form.remover_foto.data:
            deletar_imagem_antiga(current_user.foto_perfil)
            current_user.foto_perfil = '' 

        if form.foto.data:
            nome_foto = salvar_imagem_perfil(form.foto.data)
            deletar_imagem_antiga(current_user.foto_perfil)
            current_user.foto_perfil = nome_foto

        if form.remover_banner.data:
            deletar_imagem_antiga(current_user.banner_perfil)
            current_user.banner_perfil = '' 

        if form.banner.data:
            nome_banner = salvar_imagem_perfil(form.banner.data)
            deletar_imagem_antiga(current_user.banner_perfil)
            current_user.banner_perfil = nome_banner


        # Salva os textos
        current_user.bio = form.bio.data
        current_user.curso = form.curso.data
        current_user.campus = form.campus.data

        db.session.commit()
        flash('Perfil atualizado com sucesso!', 'success')
        return redirect(url_for('main.tela_perfil'))

    meus_posts = Topico.query.filter_by(autor_id=current_user.id).order_by(Topico.criado_em.desc()).all()
    meus_materiais = Material.query.filter_by(autor_id=current_user.id).order_by(Material.data_upload.desc()).all()
    meus_salvos_query = Topico.query.join(PostSalvo).filter(PostSalvo.user_id == current_user.id)
    meus_salvos = meus_salvos_query.order_by(desc(PostSalvo.id)).all()
    minhas_comunidades = current_user.comunidades_seguidas
    minhas_denuncias = Denuncia.query.filter_by(denunciante_id=current_user.id)\
                                     .order_by(Denuncia.data_envio.desc())\
                                     .all()
    return render_template(
        'tela_perfil.html',
        form=form,
        posts=meus_posts,
        materiais=meus_materiais,
        salvos=meus_salvos,
        comunidades=minhas_comunidades,
        denuncias=minhas_denuncias
    )



@main_bp.route('/denuncia/resolver/<int:denuncia_id>', methods=['POST'])
@login_required
def resolver_denuncia(denuncia_id):
    if not current_user.is_admin:
        return redirect(url_for('main.tela_inicial'))

    denuncia = Denuncia.query.get_or_404(denuncia_id)
    denuncia.status = 'Resolvida'

    try:
        db.session.commit()
        flash('Denúncia resolvida.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro: {e}', 'danger')

    return redirect(url_for('main.tela_admin'))


@main_bp.route('/denuncia/excluir/<int:denuncia_id>', methods=['POST'])
@login_required
def excluir_denuncia(denuncia_id):
    if not current_user.is_admin:
        return redirect(url_for('main.tela_inicial'))

    denuncia = Denuncia.query.get_or_404(denuncia_id)
    try:
        db.session.delete(denuncia)
        db.session.commit()
        flash('Denúncia excluída.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro: {e}', 'danger')

    return redirect(url_for('main.tela_admin'))

@main_bp.route('/calculadora')
@login_required
def tela_calculadora():
    suap_session = get_suap_session()
    if not suap_session:
        flash('Faça login novamente via SUAP para acessar essa funcionalidade.', 'warning')
        return redirect(url_for('auth.login_suap'))
    
    try:
        # 1. Pega os períodos para descobrir o atual
        url_periodos = "https://suap.ifrn.edu.br/api/ensino/meus-periodos-letivos/"
        resp_periodos = suap_session.get(url_periodos)
        
        boletim_data = []
        periodo_selecionado = None

        if resp_periodos.status_code == 200:
            periodos = resp_periodos.json().get('results', [])
            
            if periodos:
                # Pega o mais recente (o primeiro da lista)
                ultimo_periodo = periodos[0]
                ano = ultimo_periodo['ano_letivo']
                semestre = ultimo_periodo['periodo_letivo']
                
                periodo_selecionado = f"{ano}.{semestre}"

                # 2. Busca o boletim desse período
                url_boletim = f"https://suap.ifrn.edu.br/api/ensino/meu-boletim/{ano}/{semestre}/"
                resp_boletim = suap_session.get(url_boletim)

                if resp_boletim.status_code == 200:
                    boletim_json = resp_boletim.json()
                    lista_boletim = boletim_json.get('results', [])
                    
                    # --- LÓGICA DE PROJEÇÃO DE NOTAS ---
                    for disciplina in lista_boletim:
                        # Identifica se é semestral
                        try:
                            qtd_avaliacoes = int(disciplina.get('quantidade_avaliacoes', 4))
                        except:
                            qtd_avaliacoes = 4
                        
                        # O usuário pediu para remover a verificação por nome ("30H") e usar apenas avaliações
                        is_semestral = (qtd_avaliacoes == 2)
                        disciplina['semestral'] = is_semestral
                        
                        # Verifica se é do segundo semestre
                        is_segundo_semestre = disciplina.get('segundo_semestre', False)
                        # Garante que é booleano
                        if isinstance(is_segundo_semestre, str):
                            is_segundo_semestre = is_segundo_semestre.lower() == 'true'
                        
                        disciplina['is_segundo_semestre'] = is_segundo_semestre

                        # Se já está aprovado ou reprovado, não precisa calcular projeção
                        # (Mas a gente calcula antes de dar continue pra ajeitar os campos N3/N4 se precisar)
                        ja_finalizado = disciplina.get('situacao') in ['Aprovado', 'Reprovado']

                        if is_semestral:
                            if is_segundo_semestre:
                                # Semestral 2º Semestre: 
                                # As notas vêm em N1/N2, mas visualmente devem ir para N3/N4.
                                # Pesos: N3(2), N4(3) -> Total 5.
                                
                                # Move os valores para as chaves corretas se ainda não estiverem lá
                                if disciplina.get('nota_etapa_1'):
                                    disciplina['nota_etapa_3'] = disciplina['nota_etapa_1']
                                    disciplina['nota_etapa_1'] = None
                                if disciplina.get('nota_etapa_2'):
                                    disciplina['nota_etapa_4'] = disciplina['nota_etapa_2']
                                    disciplina['nota_etapa_2'] = None
                                    
                                pesos = {'nota_etapa_3': 2, 'nota_etapa_4': 3}
                            else:
                                # Semestral 1º Semestre: Normal (N1, N2)
                                pesos = {'nota_etapa_1': 2, 'nota_etapa_2': 3}
                                
                            meta_pontos = 300
                            peso_total = 5
                        else:
                            # Anual: N1(2), N2(2), N3(3), N4(3) -> Total 10. Meta 60 => 600 pontos
                            pesos = {'nota_etapa_1': 2, 'nota_etapa_2': 2, 'nota_etapa_3': 3, 'nota_etapa_4': 3}
                            meta_pontos = 600
                            peso_total = 10
                        
                        if ja_finalizado:
                            continue

                        pontos_acumulados = 0
                        peso_restante = 0
                        
                        # Calcula o que já tem e o que falta
                        for chave, peso in pesos.items():
                            dados_nota = disciplina.get(chave)
                            # Verifica se existe nota lançada (não é None)
                            if dados_nota and dados_nota.get('nota') is not None:
                                try:
                                    valor = float(dados_nota['nota'])
                                    pontos_acumulados += valor * peso
                                except:
                                    pass # Ignora erro de conversão
                            else:
                                peso_restante += peso
                        
                        # Se falta alguma nota, calcula a projeção
                        if peso_restante > 0:
                            pontos_necessarios = meta_pontos - pontos_acumulados
                            
                            if pontos_necessarios <= 0:
                                # Já tem pontos suficientes
                                nota_minima = 0
                            else:
                                import math
                                # Divide o que falta pelo peso que resta
                                nota_minima = math.ceil(pontos_necessarios / peso_restante)
                                
                                # Limita a 100
                                if nota_minima > 100:
                                    nota_minima = 100 
                            
                            # Injeta a sugestão no dicionário da disciplina
                            disciplina['nota_sugerida'] = int(nota_minima)
                        
                        # Calcula Média Parcial (considerando zeros para notas não lançadas)
                        if disciplina.get('media_disciplina') is None:
                            try:
                                # Divide pelo peso total correto (5 ou 10)
                                media_parcial = pontos_acumulados / peso_total
                                disciplina['media_parcial'] = int(media_parcial)
                            except:
                                pass
                            
                    boletim_data = lista_boletim
                else:
                    flash(f"Erro ao buscar boletim: {resp_boletim.status_code}", 'danger')
            else:
                flash("Nenhum período letivo encontrado.", 'info')
            #print(boletim_data)
            return render_template('calculadora.html', boletim=boletim_data, periodo=periodo_selecionado)
        else:
            flash(f"Erro ao buscar períodos: {resp_periodos.status_code}", 'danger')
            return render_template('calculadora.html', boletim=[], periodo=None)
            
    except Exception as e:
        flash(f"Erro na conexão com SUAP: {e}", 'danger')
        return render_template('calculadora.html', boletim=[], periodo=None)

@main_bp.route('/materiais')
@login_required
def tela_materiais():
    """Exibe a biblioteca de materiais com filtros, pesquisa e ordenação."""
    # Parâmetros da URL
    categoria_filtro = request.args.get('categoria')
    termo_pesquisa = request.args.get('q')
    ordenar_por = request.args.get('ordenarPor', 'recente')  # recente, baixados, antigos
    filtro_favoritos = request.args.get('filtro') == 'favoritos'
    filtro_meus = request.args.get('filtro') == 'meus'

    query_base = Material.query

    # Estatísticas (apenas para 'Meus Materiais')
    total_downloads = 0
    total_favoritos = 0

    # Aplicar filtros
    if filtro_favoritos:
        query_base = query_base.filter(Material.favoritado_por.any(id=current_user.id))
    elif filtro_meus:
        query_base = query_base.filter(Material.autor_id == current_user.id)
        
        # Calcular estatísticas
        total_downloads = db.session.query(func.sum(Material.download_count))\
            .filter(Material.autor_id == current_user.id).scalar() or 0
        
        total_favoritos = db.session.query(func.count(material_favoritos.c.user_id))\
            .join(Material, material_favoritos.c.material_id == Material.id)\
            .filter(Material.autor_id == current_user.id).scalar() or 0

    if categoria_filtro and categoria_filtro != 'Todas':
        query_base = query_base.filter(Material.categoria == categoria_filtro)

    # Ordenação
    if ordenar_por == 'baixados':
        query_base = query_base.order_by(Material.download_count.desc())
    elif ordenar_por == 'antigos':
        query_base = query_base.order_by(Material.data_upload.asc())
    else:
        query_base = query_base.order_by(Material.download_count.desc())

    materiais_query = query_base.all()

    # Pesquisa fuzzy (se houver termo)
    if termo_pesquisa:
        resultados_fuzzy = []
        for material in materiais_query:
            texto_completo = f"{material.titulo} {material.descricao or ''} {material.autor.name}"
            score = fuzz.partial_ratio(termo_pesquisa.lower(), texto_completo.lower())
            if score > 60:
                resultados_fuzzy.append((material, score))
        resultados_fuzzy.sort(key=lambda x: x[1], reverse=True)
        materiais_query = [material for material, score in resultados_fuzzy]

    # Agrupamento por categoria
    materiais_agrupados = {}
    for material in materiais_query:
        categoria = material.categoria or "Geral"
        if categoria not in materiais_agrupados:
            materiais_agrupados[categoria] = []
        materiais_agrupados[categoria].append(material)
    
    materiais_agrupados = dict(sorted(materiais_agrupados.items()))
    
    # IDs dos favoritos do usuário
    favoritos_ids = [m.id for m in current_user.materiais_favoritos_rel]

    return render_template(
        'tela_materiais.html',
        materiais_agrupados=materiais_agrupados,
        materiais_lista=materiais_query,
        categorias=CATEGORIAS_PADRAO,
        categoria_selecionada=categoria_filtro,
        termo_pesquisado=termo_pesquisa,
        ordenacao_selecionada=ordenar_por,
        favoritos_ids=favoritos_ids,
        filtro_favoritos=filtro_favoritos,
        filtro_meus=filtro_meus,
        total_downloads=total_downloads,
        total_favoritos=total_favoritos
    )


@main_bp.route('/materiais/adicionar', methods=['POST'])
@login_required
@limiter.limit("10 per hour")
def adicionar_material():
    """Adiciona um novo material (arquivo ou link externo)."""
    try:
        # Sanitização dos inputs
        titulo = sanitize_input(request.form.get('materialTitulo', ''))
        descricao = sanitize_input(request.form.get('materialDescricao', ''))
        tags_input = sanitize_input(request.form.get('materialTags', ''))
        categoria = request.form.get('materialCategoria')
        tipo_upload = request.form.get('tipoUpload')
        link_externo = request.form.get('materialLink')

        arquivo = request.files.get('materialArquivo')
        imagem_capa = request.files.get('materialCapa')

        # Validações
        if not titulo:
            flash('O título é obrigatório.', 'danger')
            return redirect(url_for('main.tela_materiais'))

        if categoria not in CATEGORIAS_PADRAO:
            categoria = "Geral"

        db_path = None
        link_final = None

        # Processar arquivo ou link
        if tipo_upload == 'link':
            if not link_externo:
                flash('Para adicionar um link, você deve colar a URL.', 'danger')
                return redirect(url_for('main.tela_materiais'))
            link_final = sanitize_input(link_externo)
        else:
            if not arquivo or not arquivo.filename:
                flash('Selecione um arquivo para enviar.', 'danger')
                return redirect(url_for('main.tela_materiais'))

            if not allowed_file(arquivo.filename):
                flash('Tipo de arquivo não permitido. Extensões válidas: PDF, DOC, IMG, MP4, etc.', 'danger')
                return redirect(url_for('main.tela_materiais'))

            filename = secure_filename(arquivo.filename)
            ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            filename = f"mat_{ts}_{filename}"
            upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            arquivo.save(upload_path)
            db_path = f"/static/uploads/{filename}"

        # Processar imagem de capa
        capa_db_path = None
        if imagem_capa and imagem_capa.filename:
            if allowed_file(imagem_capa.filename):
                capa_filename = secure_filename(imagem_capa.filename)
                ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                capa_filename = f"capa_{ts}_{capa_filename}"
                capa_path = os.path.join(current_app.config['UPLOAD_FOLDER'], capa_filename)
                imagem_capa.save(capa_path)
                capa_db_path = f"/static/uploads/{capa_filename}"

        # Criar material
        novo_material = Material(
            titulo=titulo,
            descricao=descricao,
            arquivo_path=db_path,
            link_externo=link_final,
            imagem_capa=capa_db_path,
            categoria=categoria,
            autor_id=current_user.id
        )

        # Processar tags (máximo 3)
        if tags_input:
            tags_list = [t.strip() for t in tags_input.split(',') if t.strip()][:3]
            for tag_nome in tags_list:
                tag = Tag.query.filter_by(nome=tag_nome).first()
                if not tag:
                    tag = Tag(nome=tag_nome)
                    db.session.add(tag)
                novo_material.tags.append(tag)

        db.session.add(novo_material)
        db.session.commit()
        flash('Material publicado com sucesso!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao publicar material: {str(e)}', 'danger')

    return redirect(url_for('main.tela_materiais'))


@main_bp.route('/materiais/download/<int:material_id>')
@login_required
@limiter.limit("100 per hour")
def download_material(material_id: int):
    """Incrementa contador e faz download/redirecionamento do material."""
    material = Material.query.get_or_404(material_id)

    # Incrementa contador de acessos
    material.download_count += 1
    db.session.commit()

    # Link externo: redirecionar
    if material.link_externo:
        return redirect(material.link_externo)

    # Arquivo local: enviar para download
    if material.arquivo_path:
        try:
            filename = os.path.basename(material.arquivo_path)
            directory = os.path.join(current_app.root_path, 'static', 'uploads')
            return send_from_directory(directory, filename, as_attachment=True)
        except FileNotFoundError:
            flash('Arquivo não encontrado no servidor.', 'danger')
            return redirect(url_for('main.tela_materiais'))

    flash('Este material não possui arquivo para download.', 'warning')
    return redirect(url_for('main.tela_materiais'))


@main_bp.route('/materiais/favoritar/<int:material_id>', methods=['POST'])
@login_required
@limiter.limit("50 per hour")
def favoritar_material(material_id):
    material = Material.query.get_or_404(material_id)

    if current_user in material.favoritado_por:
        material.favoritado_por.remove(current_user)
    else:
        material.favoritado_por.append(current_user)

    db.session.commit()
    return redirect(request.referrer or url_for('main.tela_materiais'))


@main_bp.route('/materiais/excluir/<int:material_id>', methods=['POST'])
@login_required
@limiter.limit("20 per hour")
def excluir_material(material_id: int):
    """Exclui um material e seu arquivo físico (se houver)."""
    material = Material.query.get_or_404(material_id)

    # Verificar permissões
    if not current_user.is_admin and material.autor_id != current_user.id:
        flash('Você não tem permissão para excluir este material.', 'danger')
        return redirect(url_for('main.tela_materiais'))

    try:
        # Excluir arquivo físico se existir
        if material.arquivo_path:
            filename = os.path.basename(material.arquivo_path)
            arquivo_path_abs = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(arquivo_path_abs):
                os.remove(arquivo_path_abs)
        
        # Excluir imagem de capa se existir
        if material.imagem_capa:
            capa_filename = os.path.basename(material.imagem_capa)
            capa_path_abs = os.path.join(current_app.config['UPLOAD_FOLDER'], capa_filename)
            if os.path.exists(capa_path_abs):
                os.remove(capa_path_abs)

        db.session.delete(material)
        db.session.commit()
        flash('Material excluído com sucesso.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir material: {str(e)}', 'danger')
        
    return redirect(url_for('main.tela_materiais'))


@main_bp.route('/suporte', methods=['GET', 'POST'])
@login_required
def suporte():
    if request.method == 'POST':
        titulo = request.form.get('title')
        descricao = request.form.get('description')

        # Validação de campos obrigatórios
        if not descricao:
            flash('Descrição obrigatória.', 'danger')
            return redirect(url_for('main.suporte'))
        
        if not titulo:
            flash('Título obrigatório.', 'danger')
            return redirect(url_for('main.suporte'))

        # Criar a denúncia
        nova_denuncia = Denuncia(
            titulo=titulo,
            descricao=descricao,
            denunciante_id=current_user.id
        )

        try:
            db.session.add(nova_denuncia)
            db.session.commit()
            flash('Denúncia enviada com sucesso.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Ocorreu um erro ao enviar a denúncia: {e}', 'danger')

        return redirect(url_for('main.suporte'))

    # Para exibir FAQs ou outros dados
    termo_busca = request.args.get('busca', '')
    faqs_resultados = []

    if termo_busca:
        faqs_resultados = FAQ.query.filter(
            or_(
                FAQ.pergunta.ilike(f'%{termo_busca}%'),
                FAQ.resposta.ilike(f'%{termo_busca}%')
            )
        ).all()

    faqs_recentes = FAQ.query.order_by(FAQ.id.desc()).limit(4).all()

    return render_template(
        'tela_suporte.html',
        faqs_recentes=faqs_recentes,
        faqs_resultados=faqs_resultados,
        termo_busca=termo_busca
    )

# PARTE ADMIN IIIIINNNNNNNN
@main_bp.route('/tela_admin')
@login_required
def tela_admin():
    if current_user.is_admin:
        # Pega a quantidade exata de usuarios cadastrados
        users_count = User.query.count()

        # Usuários normais
        usuarios = User.query.filter_by(is_admin=False).all()

        # ----- SISTEMA DE FILTRO -----
    filtro = request.args.get("filtro", "aberto")  
    page = int(request.args.get("page", 1))
    por_pagina = 4

    # Filtragem
    if filtro == "aberto":
        query = Denuncia.query.filter_by(status="Recebida")
    elif filtro == "resolvido":
        query = Denuncia.query.filter_by(status="Resolvida")
    else:
        query = Denuncia.query

    total = query.count()

    # Paginação
    denuncias = query.order_by(Denuncia.data_envio.desc()) \
                     .offset((page - 1) * por_pagina) \
                     .limit(por_pagina) \
                     .all()

    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)

    # Dados gerais
    total_abertas = Denuncia.query.filter_by(status='Recebida').count()
    total_resolvidas = Denuncia.query.filter_by(status='Resolvida').count()
    total_denuncias = total_abertas + total_resolvidas

    # Limitador de caracteres
    limite_titulo = 40
    limite_descricao = 60


    return render_template(
        "tela_admin.html",
        users_count=users_count,
        usuarios=usuarios,
        denuncias=denuncias,
        filtro=filtro,
        page=page,
        total_paginas=total_paginas,
        total_abertas=total_abertas,
        total_resolvidas=total_resolvidas,
        total_denuncias=total_denuncias,
        limite_titulo=limite_titulo,
        limite_descricao=limite_descricao
    )


@main_bp.route('/enquete/votar/<int:opcao_id>', methods=['POST'])
@login_required
def votar_enquete(opcao_id):
    opcao = EnqueteOpcao.query.get_or_404(opcao_id)
    topico = opcao.topico
    
    # Verifica se usuário já votou NESTE tópico (qualquer opção dele)
    voto_existente = EnqueteVoto.query.join(EnqueteOpcao).filter(
        EnqueteVoto.user_id == current_user.id,
        EnqueteOpcao.topico_id == topico.id
    ).first()
    
    if voto_existente:
        flash('Você já votou nesta enquete.', 'warning')
    else:
        novo_voto = EnqueteVoto(user_id=current_user.id, opcao_id=opcao.id)
        db.session.add(novo_voto)
        db.session.commit()
        flash('Voto computado!', 'success')
        
    return redirect(request.referrer)

@main_bp.route('/forum/<int:topico_id>/fixar', methods=['POST'])
@login_required
def fixar_post(topico_id):
    topico = Topico.query.get_or_404(topico_id)
    
    # Apenas moderadores ou dono da comunidade podem fixar
    if not topico.comunidade or (current_user not in topico.comunidade.moderadores and current_user.id != topico.comunidade.criador_id):
        flash('Sem permissão.', 'danger')
        return redirect(request.referrer)
    
    # Inverte o status (se ta fixado, desafixa e vice-versa)
    topico.fixado = not topico.fixado
    db.session.commit()
    
    msg = 'Tópico fixado no topo!' if topico.fixado else 'Tópico desafixado.'
    flash(msg, 'success')
    return redirect(request.referrer)

# No final de app/routes.py, ou junto com as outras rotas de fórum

@main_bp.route('/post/<int:topico_id>')
@login_required
def ver_post_individual(topico_id):
    topico = Topico.query.get_or_404(topico_id)
    
    # Verifica acesso se for comunidade restrita
    if topico.comunidade and topico.comunidade.tipo_acesso == 'Restrito':
        if current_user not in topico.comunidade.membros:
            flash('Este post é privado.', 'danger')
            return redirect(url_for('main.tela_inicial'))

    likes_usuario = [l.topico_id for l in PostLike.query.filter_by(user_id=current_user.id).all()]
    likes_respostas_usuario = [l.resposta_id for l in RespostaLike.query.filter_by(user_id=current_user.id).all()]
    
    votos_usuario = []
    ids = db.session.query(EnqueteVoto.opcao_id).filter(EnqueteVoto.user_id == current_user.id).all()
    votos_usuario = [v[0] for v in ids]

    return render_template(
        'tela_post.html', 
        topico=topico,
        likes_usuario=likes_usuario,
        likes_respostas_usuario=likes_respostas_usuario,
        votos_usuario=votos_usuario
    )
