from flask import render_template, request, redirect, url_for, flash, current_app, send_from_directory, Blueprint
from flask_login import login_required, current_user
from sqlalchemy import or_, desc, func
from werkzeug.utils import secure_filename
import os
import datetime
from thefuzz import fuzz
# Imports completos dos modelos (Incluindo as novas tabelas)
from app.models import (
    Material, User, FAQ, Denuncia, Noticia, Evento, Perfil, 
    Topico, Resposta, PostSalvo, PostLike, Notificacao, 
    Comunidade, SolicitacaoParticipacao, RespostaLike, Tag
)
from app.extensions import db
from app.forms import ProfileForm

main_bp = Blueprint('main', __name__)

@main_bp.after_request
def add_header(response):
    """
    Adiciona cabeçalhos para evitar cache em rotas protegidas.
    """
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, public, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# --- FILTRO DE DATA (Para mostrar '21/11 às 14:30' no HTML) ---
@main_bp.app_template_filter('format_data_br')
def format_data_br(dt):
    if dt is None:
        return ""
    # Converte UTC para Horário de Brasília (UTC-3)
    dt_brasil = dt - datetime.timedelta(hours=3)
    return dt_brasil.strftime('%d/%m às %H:%M')


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
    - Últimas notícias
    - Próximos eventos
    """
    # Se for admin, redireciona para o painel dele
    if current_user.is_admin:
        return redirect(url_for('main.tela_admin'))

    # Busca notícias e eventos
    noticias = Noticia.query.order_by(Noticia.data_postagem.desc()).limit(4).all()
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
    """
    Lista todas as comunidades disponíveis e permite buscar.
    """
    busca = request.args.get('q')
    categoria_filtro = request.args.get('categoria')
    
    query = Comunidade.query

    # Filtro por Nome
    if busca:
        query = query.filter(Comunidade.nome.ilike(f'%{busca}%'))
    
    # Filtro por Categoria
    if categoria_filtro and categoria_filtro != 'Todas':
        query = query.filter(Comunidade.categoria == categoria_filtro)

    # Ordenação alfabética
    comunidades = query.order_by(Comunidade.nome).all()
    
    # Busca categorias para o menu
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
    """
    Cria uma nova comunidade com suporte a imagem, categoria e tipo.
    """
    try:
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        categoria = request.form.get('categoria')
        tipo = request.form.get('tipo')
        imagem = request.files.get('imagem')
        
        # Validação básica
        if not nome or not descricao:
            flash('Nome e descrição são obrigatórios.', 'warning')
            return redirect(url_for('main.tela_comunidades'))
            
        # Verifica se já existe
        if Comunidade.query.filter(func.lower(Comunidade.nome) == func.lower(nome)).first():
            flash(f'A comunidade "{nome}" já existe. Tente outro nome.', 'danger')
            return redirect(url_for('main.tela_comunidades'))

        # Cria a comunidade
        nova_com = Comunidade(
            nome=nome,
            descricao=descricao,
            categoria=categoria,
            tipo_acesso=tipo,
            criador_id=current_user.id
        )
        
        # Salvar Imagem da Comunidade
        if imagem and imagem.filename:
            filename = secure_filename(imagem.filename)
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            filename = f"com_{timestamp}_{filename}"
            
            upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            imagem.save(upload_path)
            nova_com.imagem_url = f"/static/uploads/{filename}"
        
        # O criador entra automaticamente e vira moderador
        nova_com.membros.append(current_user)
        nova_com.moderadores.append(current_user)
        
        db.session.add(nova_com)
        db.session.commit()
        
        flash(f'Comunidade "{nome}" criada com sucesso!', 'success')
        return redirect(url_for('main.ver_comunidade', comunidade_id=nova_com.id))

    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao criar comunidade: {e}', 'danger')
        return redirect(url_for('main.tela_comunidades'))


@main_bp.route('/comunidade/<int:comunidade_id>/participar')
@login_required
def participar_comunidade(comunidade_id):
    """
    Alterna entre Entrar e Sair de uma comunidade.
    """
    comunidade = Comunidade.query.get_or_404(comunidade_id)
    
    # SAIR
    if current_user in comunidade.membros:
        comunidade.membros.remove(current_user)
        
        # Se for mod (e não dono), perde o cargo ao sair
        if current_user in comunidade.moderadores and comunidade.criador_id != current_user.id:
            comunidade.moderadores.remove(current_user)
        
        flash(f'Você saiu de {comunidade.nome}.', 'info')
        db.session.commit()
        return redirect(request.referrer or url_for('main.tela_comunidades'))

    # ENTRAR
    if comunidade.tipo_acesso == 'Restrito':
        # Verifica se já pediu
        solicitacao = SolicitacaoParticipacao.query.filter_by(user_id=current_user.id, comunidade_id=comunidade.id).first()
        if solicitacao:
            flash('Solicitação já enviada. Aguarde aprovação.', 'warning')
        else:
            nova_sol = SolicitacaoParticipacao(user_id=current_user.id, comunidade_id=comunidade.id)
            db.session.add(nova_sol)
            db.session.commit()
            flash('Solicitação enviada aos moderadores.', 'success')
    else:
        # Público: Entra direto
        comunidade.membros.append(current_user)
        db.session.commit()
        flash(f'Bem-vindo ao {comunidade.nome}!', 'success')
        
    return redirect(request.referrer or url_for('main.tela_comunidades'))


@main_bp.route('/c/<int:comunidade_id>')
@login_required
def ver_comunidade(comunidade_id):
    """
    Visualiza o feed de uma comunidade específica.
    """
    comunidade = Comunidade.query.get_or_404(comunidade_id)
    
    # Controle de Acesso (Privacidade)
    tem_acesso = True
    if comunidade.tipo_acesso == 'Restrito' and current_user not in comunidade.membros:
        tem_acesso = False
        topicos = []
    else:
        # Busca posts APENAS desta comunidade
        topicos = Topico.query.filter_by(comunidade_id=comunidade.id).order_by(desc(Topico.criado_em)).all()
    
    # Dados auxiliares para os botões
    likes_usuario = [l.topico_id for l in PostLike.query.filter_by(user_id=current_user.id).all()]
    salvos_usuario = [s.topico_id for s in PostSalvo.query.filter_by(user_id=current_user.id).all()]
    likes_respostas_usuario = [l.resposta_id for l in RespostaLike.query.filter_by(user_id=current_user.id).all()]
    
    # Verifica solicitação pendente
    solicitacao_pendente = False
    if not tem_acesso:
        sol = SolicitacaoParticipacao.query.filter_by(user_id=current_user.id, comunidade_id=comunidade.id).first()
        if sol: solicitacao_pendente = True

    # Sugestões Inteligentes (Mesma Categoria)
    sugestoes = Comunidade.query.filter(
        Comunidade.categoria == comunidade.categoria,
        Comunidade.id != comunidade.id
    ).limit(3).all()
    
    if not sugestoes:
        sugestoes = Comunidade.query.filter(Comunidade.id != comunidade.id).limit(3).all()

    return render_template(
        'tela_comunidade_detalhe.html', 
        comunidade=comunidade, 
        topicos=topicos,
        likes_usuario=likes_usuario,
        salvos_usuario=salvos_usuario,
        likes_respostas_usuario=likes_respostas_usuario,
        tem_acesso=tem_acesso,
        solicitacao_pendente=solicitacao_pendente,
        sugestoes=sugestoes
    )


# ===================================================================
# GESTÃO E MODERAÇÃO DE COMUNIDADES
# ===================================================================

@main_bp.route('/c/<int:comunidade_id>/configurar', methods=['GET', 'POST'])
@login_required
def configurar_comunidade(comunidade_id):
    """
    Dashboard da Comunidade (Apenas para Dono e Moderadores).
    """
    comunidade = Comunidade.query.get_or_404(comunidade_id)
    
    # Verifica permissão
    eh_dono = (comunidade.criador_id == current_user.id)
    eh_mod = (current_user in comunidade.moderadores)
    
    if not eh_dono and not eh_mod and not current_user.is_admin:
        flash('Você não tem permissão para configurar esta comunidade.', 'danger')
        return redirect(url_for('main.ver_comunidade', comunidade_id=comunidade.id))

    if request.method == 'POST':
        # Atualiza informações básicas
        comunidade.descricao = request.form.get('descricao')
        comunidade.regras = request.form.get('regras')
        
        # Upload de Imagem (Logo/Banner)
        imagem = request.files.get('imagem_comunidade')
        if imagem and imagem.filename:
            filename = secure_filename(imagem.filename)
            ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            fname = f"com_{ts}_{filename}"
            path = os.path.join(current_app.config['UPLOAD_FOLDER'], fname)
            
            try:
                imagem.save(path)
                comunidade.imagem_url = f"/static/uploads/{fname}"
            except Exception as e:
                flash(f'Erro ao salvar imagem: {e}', 'danger')

        db.session.commit()
        flash('Configurações da comunidade atualizadas!', 'success')
        return redirect(url_for('main.configurar_comunidade', comunidade_id=comunidade.id))
    
    # Busca solicitações pendentes
    solicitacoes = []
    if comunidade.tipo_acesso == 'Restrito':
        solicitacoes = SolicitacaoParticipacao.query.filter_by(comunidade_id=comunidade.id).all()

    return render_template('tela_comunidade_config.html', comunidade=comunidade, solicitacoes=solicitacoes)


@main_bp.route('/c/<int:comunidade_id>/promover/<int:user_id>')
@login_required
def promover_moderador(comunidade_id, user_id):
    """
    Promove ou rebaixa um membro a moderador.
    """
    comunidade = Comunidade.query.get_or_404(comunidade_id)
    alvo = User.query.get_or_404(user_id)
    
    if comunidade.criador_id != current_user.id and not current_user.is_admin:
        flash('Apenas o dono pode gerenciar moderadores.', 'danger')
        return redirect(url_for('main.configurar_comunidade', comunidade_id=comunidade_id))
        
    if alvo not in comunidade.moderadores:
        comunidade.moderadores.append(alvo)
        flash(f'{alvo.name} agora é um moderador!', 'success')
    else:
        comunidade.moderadores.remove(alvo)
        flash(f'{alvo.name} não é mais moderador.', 'info')
        
    db.session.commit()
    return redirect(url_for('main.configurar_comunidade', comunidade_id=comunidade_id))


@main_bp.route('/c/<int:comunidade_id>/solicitacoes/<int:sol_id>/<acao>')
@login_required
def gerenciar_solicitacao(comunidade_id, sol_id, acao):
    """
    Aceita ou Recusa solicitações de entrada.
    """
    comunidade = Comunidade.query.get_or_404(comunidade_id)
    
    if current_user not in comunidade.moderadores and not current_user.is_admin:
        return redirect(url_for('main.ver_comunidade', comunidade_id=comunidade_id))
        
    solicitacao = SolicitacaoParticipacao.query.get_or_404(sol_id)
    
    if acao == 'aceitar':
        usuario = User.query.get(solicitacao.user_id)
        comunidade.membros.append(usuario)
        db.session.delete(solicitacao)
        try:
            notificacao = Notificacao(
                mensagem=f"Sua solicitação para entrar na comunidade {comunidade.nome} foi aceita.",
                link_url=url_for('main.ver_comunidade', comunidade_id=comunidade.id),
                usuario_id=usuario.id
            )
            db.session.add(notificacao)
            db.session.commit()
            flash(f'{usuario.name} foi aceito na comunidade!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao criar notificação: {e}', 'danger')
    elif acao == 'recusar':
        try:
            notificacao = Notificacao(
                mensagem=f"Sua solicitação para entrar na comunidade {comunidade.nome} foi recusada.",
                link_url=url_for('main.tela_comunidades'),
                usuario_id=solicitacao.user_id
            )
            db.session.add(notificacao)
            db.session.delete(solicitacao)
            db.session.commit()
            flash('Solicitação recusada.', 'info')
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao criar notificação: {e}', 'danger')
        
    return redirect(url_for('main.configurar_comunidade', comunidade_id=comunidade_id))


# ===================================================================
# FÓRUM GERAL E POSTAGEM (ATUALIZADO)
# ===================================================================

@main_bp.route('/forum')
@login_required
def tela_foruns():
    """
    Exibe o feed principal com lógica de PESQUISA, FILTRO e ORDENAÇÃO.
    """
    termo_pesquisa = request.args.get('q')
    ordenar_por = request.args.get('ordenarPor')
    filtro = request.args.get('filtro')

    query = Topico.query

    # Filtro de Pesquisa
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
        # Padrão: mais recente
        query = query.order_by(desc(Topico.criado_em))

    topicos = query.all()
    
    likes_usuario = [l.topico_id for l in PostLike.query.filter_by(user_id=current_user.id).all()]
    salvos_usuario = [s.topico_id for s in PostSalvo.query.filter_by(user_id=current_user.id).all()]

    # Fetch notifications for current user
    notificacoes = Notificacao.query.filter_by(usuario_id=current_user.id, lida=False).order_by(desc(Notificacao.data_criacao)).limit(30).all()

    return render_template(
        'tela_foruns.html', 
        topicos=topicos,
        likes_usuario=likes_usuario,
        salvos_usuario=salvos_usuario,
        termo_pesquisado=termo_pesquisa,
        ordenacao_selecionada=ordenar_por,
        filtro_selecionado=filtro,
        notificacoes=notificacoes
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


@main_bp.route('/forum/postar', methods=['POST'])
@login_required
def criar_post():
    """
    Cria um novo post (COM UPLOAD DE IMAGEM).
    """
    conteudo = request.form.get('conteudo_post')
    comunidade_id = request.form.get('comunidade_id') # ID da comunidade
    imagem = request.files.get('midia_post') # Arquivo de imagem

    if not conteudo and not imagem:
        flash('O post não pode ficar vazio.', 'warning')
        return redirect(request.referrer or url_for('main.tela_foruns'))

    # Define um título baseado na primeira linha
    linhas = conteudo.split('\n', 1) if conteudo else ["Nova Imagem"]
    titulo = linhas[0].strip()[:150] if conteudo else "Imagem"
    if not titulo:
        titulo = "Novo Post"

    # Converte comunidade_id para inteiro se existir
    com_id = int(comunidade_id) if comunidade_id else None

    novo_topico = Topico(
        titulo=titulo,
        conteudo=conteudo if conteudo else "",
        autor_id=current_user.id,
        comunidade_id=com_id
    )

    # Salvar imagem se houver
    if imagem and imagem.filename:
        filename = secure_filename(imagem.filename)
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"post_{ts}_{filename}"
        path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        
        try:
            imagem.save(path)
            novo_topico.imagem_post = f"/static/uploads/{filename}"
        except Exception as e:
            flash(f'Erro ao salvar imagem: {e}', 'danger')
    
    db.session.add(novo_topico)
    db.session.commit()

    # Create notifications for community members about the new post (excluding author)
    if com_id:
        comunidade = Comunidade.query.get(com_id)
        membros_ids = [membro.id for membro in comunidade.membros if membro.id != current_user.id]
        try:
            for usuario_id in membros_ids:
                mensagem = f"Novo post na comunidade {comunidade.nome}: {titulo}"
                link = url_for('main.ver_comunidade', comunidade_id=com_id)
                notificacao = Notificacao(mensagem=mensagem, link_url=link, usuario_id=usuario_id)
                db.session.add(notificacao)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao criar notificações: {e}', 'danger')

    flash('Post criado com sucesso!', 'success')
    
    if com_id:
        return redirect(url_for('main.ver_comunidade', comunidade_id=com_id))

    return redirect(url_for('main.tela_foruns'))


@main_bp.route('/forum/<int:topico_id>/comentar', methods=['POST'])
@login_required
def comentar_post(topico_id):
    """
    Cria um comentário (COM UPLOAD E ANINHAMENTO).
    """
    conteudo = request.form.get('conteudo_comentario')
    imagem = request.files.get('midia_comentario')
    parent_id = request.form.get('parent_id') # ID do Pai
    
    topico = Topico.query.get_or_404(topico_id)

    if not conteudo and not imagem:
        flash('O comentário não pode ficar vazio.', 'warning')
        return redirect(request.referrer)

    pid = int(parent_id) if parent_id else None

    nova_resposta = Resposta(
        conteudo=conteudo if conteudo else "",
        topico_id=topico.id,
        autor_id=current_user.id,
        parent_id=pid # Salva o aninhamento
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
    
    # Notificação
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

        # Se for comentário no post
        elif topico.autor_id != current_user.id:
            db.session.add(Notificacao(
                mensagem=f"{current_user.name} comentou no seu post.", 
                link_url=link_destino, 
                usuario_id=topico.autor_id
            ))

        # Aqui: Notificar também os outros membros da comunidade (exceto autor do comentário e autor do post)
        if topico.comunidade_id:
            comunidade = Comunidade.query.get(topico.comunidade_id)
            membros_notificar = [membro.id for membro in comunidade.membros if membro.id not in (current_user.id, topico.autor_id)]
            for usuario_id in membros_notificar:
                db.session.add(Notificacao(
                    mensagem=f"{current_user.name} comentou em um post da comunidade {comunidade.nome}.",
                    link_url=link_destino,
                    usuario_id=usuario_id
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

@main_bp.route('/mapa')
@login_required
def tela_mapa():
    return render_template('tela_mapa.html')

@main_bp.route('/perfil', methods=['GET', 'POST'])
@login_required 
def tela_perfil():
    form = ProfileForm(obj=current_user.perfil)
    
    if form.validate_on_submit():
        if not current_user.perfil:
            perfil = Perfil(user_id=current_user.id)
            db.session.add(perfil)
        form.populate_obj(current_user.perfil)
        
        try:
            db.session.commit()
            flash('Perfil atualizado com sucesso!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar o perfil: {e}', 'danger')
        return redirect(url_for('main.tela_perfil'))

    meus_posts = Topico.query.filter_by(autor_id=current_user.id).order_by(Topico.criado_em.desc()).all()
    meus_materiais = Material.query.filter_by(autor_id=current_user.id).order_by(Material.data_upload.desc()).all()
    
    # Busca os Tópicos salvos
    meus_salvos_query = Topico.query.join(PostSalvo).filter(PostSalvo.user_id == current_user.id)
    meus_salvos = meus_salvos_query.order_by(desc(PostSalvo.id)).all()

    return render_template(
        'tela_perfil.html', 
        form=form,
        posts=meus_posts,
        materiais=meus_materiais,
        salvos=meus_salvos
    )

@main_bp.route('/denuncias')
@login_required
def tela_denuncias():
    if not current_user.is_admin:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('main.tela_inicial'))
        
    denuncias_abertas = Denuncia.query.filter_by(status='Recebida').order_by(Denuncia.data_envio.desc()).all()
    total_abertas = len(denuncias_abertas)
    total_resolvidas = Denuncia.query.filter_by(status='Resolvida').count()
    total_denuncias = total_abertas + total_resolvidas
    
    return render_template(
        'tela_denuncias.html', 
        denuncias=denuncias_abertas,
        total_abertas=total_abertas,
        total_resolvidas=total_resolvidas,
        total_denuncias=total_denuncias
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
        
    return redirect(url_for('main.tela_denuncias'))

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
        
    return redirect(url_for('main.tela_denuncias'))


@main_bp.route('/materiais')
@login_required
def tela_materiais():
    categoria_filtro = request.args.get('categoria')
    termo_pesquisa = request.args.get('q')
    ordenar_por = request.args.get('ordenarPor', 'recente') # recente, baixados, antigos
    filtro_favoritos = request.args.get('filtro') == 'favoritos' # Novo filtro

    query_base = Material.query
    
    # Filtro de Favoritos (Meus Materiais Salvos)
    if filtro_favoritos:
        query_base = query_base.filter(Material.favoritado_por.any(id=current_user.id))

    if categoria_filtro:
        query_base = query_base.filter(Material.categoria == categoria_filtro)
    
    # Ordenação
    if ordenar_por == 'baixados':
        query_base = query_base.order_by(Material.download_count.desc())
    elif ordenar_por == 'antigos':
        query_base = query_base.order_by(Material.data_upload.asc())
    else: # recente
        query_base = query_base.order_by(Material.data_upload.desc())

    materiais_query = query_base.all()

    if termo_pesquisa:
        resultados_fuzzy = []
        for material in materiais_query:
            texto_completo = f"{material.titulo} {material.descricao or ''}"
            score = fuzz.partial_ratio(termo_pesquisa.lower(), texto_completo.lower()) 
            if score > 60:
                resultados_fuzzy.append((material, score))
        resultados_fuzzy.sort(key=lambda x: x[1], reverse=True)
        materiais_query = [material for material, score in resultados_fuzzy]

    # Agrupamento (Mantido para compatibilidade, mas a view pode usar a lista plana se quiser)
    materiais_agrupados = {}
    for material in materiais_query:
        categoria = material.categoria if material.categoria else "Geral"
        if categoria not in materiais_agrupados:
            materiais_agrupados[categoria] = []
        materiais_agrupados[categoria].append(material)
    
    categorias_query = db.session.query(Material.categoria).distinct().order_by(Material.categoria)
    categorias = [c[0] for c in categorias_query if c[0]]
    
    # IDs dos materiais favoritados pelo usuário atual
    favoritos_ids = [m.id for m in current_user.materiais_favoritos_rel]

    return render_template(
        'tela_materiais.html', 
        materiais_agrupados=materiais_agrupados,
        materiais_lista=materiais_query, # Passando lista plana também
        categorias=categorias,
        categoria_selecionada=categoria_filtro,
        termo_pesquisado=termo_pesquisa,
        ordenacao_selecionada=ordenar_por,
        favoritos_ids=favoritos_ids,
        filtro_favoritos=filtro_favoritos
    )


@main_bp.route('/materiais/adicionar', methods=['POST'])
@login_required
def adicionar_material():
    if request.method == 'POST':
        try:
            titulo = request.form.get('materialTitulo')
            descricao = request.form.get('materialDescricao')
            arquivo = request.files.get('materialArquivo')
            imagem_capa = request.files.get('materialCapa') # Novo campo
            tags_input = request.form.get('materialTags')   # Novo campo
            
            categoria_nova = request.form.get('materialCategoriaNova')
            categoria = categoria_nova.strip().capitalize() if categoria_nova else request.form.get('materialCategoriaExistente')
            
            if not titulo or not arquivo or not arquivo.filename:
                flash('Erro: Título e Arquivo são obrigatórios.', 'danger')
                return redirect(url_for('main.tela_materiais'))

            # Salvar Arquivo Principal
            filename = secure_filename(arquivo.filename)
            ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            filename = f"mat_{ts}_{filename}" # Prefixo para evitar colisão
            
            upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            arquivo.save(upload_path)
            db_path = f"/static/uploads/{filename}"

            # Salvar Imagem de Capa (Se houver)
            capa_db_path = None
            if imagem_capa and imagem_capa.filename:
                capa_filename = secure_filename(imagem_capa.filename)
                capa_filename = f"capa_{ts}_{capa_filename}"
                capa_path = os.path.join(current_app.config['UPLOAD_FOLDER'], capa_filename)
                imagem_capa.save(capa_path)
                capa_db_path = f"/static/uploads/{capa_filename}"

            novo_material = Material(
                titulo=titulo,
                descricao=descricao,
                arquivo_path=db_path,
                imagem_capa=capa_db_path,
                categoria=categoria,
                autor_id=current_user.id 
            )
            
            # Processar Tags
            if tags_input:
                tags_list = [t.strip() for t in tags_input.split(',') if t.strip()]
                for tag_nome in tags_list:
                    # Busca tag existente ou cria nova
                    tag = Tag.query.filter_by(nome=tag_nome).first()
                    if not tag:
                        tag = Tag(nome=tag_nome)
                        db.session.add(tag)
                    novo_material.tags.append(tag)
            
            db.session.add(novo_material)
            db.session.commit()
            flash('Material adicionado com sucesso!', 'success')
        
        except Exception as e:
            db.session.rollback()
            flash(f'Erro interno: {e}', 'danger')

    return redirect(url_for('main.tela_materiais'))


@main_bp.route('/materiais/download/<int:material_id>')
@login_required
def download_material(material_id):
    material = Material.query.get_or_404(material_id)
    
    # Incrementa contador
    material.download_count += 1
    db.session.commit()
    
    try:
        directory = os.path.join(current_app.root_path, 'static', 'uploads')
        filename = os.path.basename(material.arquivo_path)
        return send_from_directory(directory, filename, as_attachment=False, conditional=True)
    except FileNotFoundError:
        flash('Arquivo não encontrado.', 'danger')
        return redirect(url_for('main.tela_materiais'))


@main_bp.route('/materiais/favoritar/<int:material_id>', methods=['POST'])
@login_required
def favoritar_material(material_id):
    material = Material.query.get_or_404(material_id)
    
    if current_user in material.favoritado_por:
        material.favoritado_por.remove(current_user)
        acao = 'removido'
    else:
        material.favoritado_por.append(current_user)
        acao = 'adicionado'
        
    db.session.commit()
    
    # Se for AJAX, retorna JSON (opcional, mas bom para UX fluida)
    # Por enquanto, redirect simples para manter consistência
    return redirect(request.referrer or url_for('main.tela_materiais'))


@main_bp.route('/materiais/excluir/<int:material_id>', methods=['POST'])
@login_required
def excluir_material(material_id):
    material = Material.query.get_or_404(material_id)
    
    if not current_user.is_admin and material.autor_id != current_user.id:
        flash('Sem permissão.', 'danger')
        return redirect(url_for('main.tela_materiais'))

    try:
        arquivo_path_abs = os.path.join(current_app.root_path, material.arquivo_path)
        if os.path.exists(arquivo_path_abs):
            os.remove(arquivo_path_abs)
        db.session.delete(material)
        db.session.commit()
        flash('Material excluído.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro: {e}', 'danger')
    return redirect(url_for('main.tela_materiais'))


@main_bp.route('/suporte', methods=['GET', 'POST'])
@login_required
def suporte():
    if request.method == 'POST':
        assunto = request.form.get('title')
        descricao = request.form.get('description')

        if not descricao:
            flash('Descrição obrigatória.', 'danger')
            return redirect(url_for('main.suporte'))

        descricao_completa = f"Assunto: {assunto}\n\n{descricao}" if assunto else descricao

        nova_denuncia = Denuncia(
            tipo_denuncia="Denúncia via Página de Suporte",
            descricao=descricao_completa,
            denunciante_id=current_user.id
        )

        try:
            db.session.add(nova_denuncia)
            db.session.commit()
            flash('Enviado com sucesso.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao enviar: {e}', 'danger')

        return redirect(url_for('main.suporte'))

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

        return render_template('tela_admin.html', users_count=users_count)
    return redirect(request.referrer)
