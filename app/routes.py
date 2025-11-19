from flask import render_template, request, redirect, url_for, flash, current_app, send_from_directory, Blueprint
from flask_login import login_required, current_user
from sqlalchemy import or_, desc, func
from werkzeug.utils import secure_filename
import os
import datetime
from thefuzz import fuzz
from app.models import Material, User, FAQ, Denuncia, Noticia, Evento, Perfil, Topico, Resposta, PostSalvo, PostLike, Notificacao
from app.extensions import db
from app.forms import ProfileForm

main_bp = Blueprint('main', __name__)

# ------------------------------------------------------------
# TELA INICIAL
# ------------------------------------------------------------

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

    # Impedindo do adm ir em outras páginas
    if current_user.is_admin:
        return redirect(url_for('main.tela_admin'))

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

# ------------------------------------------------------------
# FUNÇÕES DO FÓRUM (COMPLETAS)
# ------------------------------------------------------------

@main_bp.route('/forum')
@login_required
def tela_foruns():
    """
    ATUALIZADO: Agora inclui lógica de PESQUISA, FILTRO e ORDENAÇÃO.
    """
    
    # 1. Obter os parâmetros da URL (ex: /forum?q=teste&ordenarPor=relevancia)
    termo_pesquisa = request.args.get('q')
    ordenar_por = request.args.get('ordenarPor')
    filtro = request.args.get('filtro') # Para o filtro de "posts salvos"

    # 2. Iniciar a consulta base de Tópicos
    query = Topico.query

    # 3. Aplicar Filtro de PESQUISA (se existir)
    if termo_pesquisa:
        query = query.filter(or_(
            Topico.titulo.ilike(f'%{termo_pesquisa}%'),
            Topico.conteudo.ilike(f'%{termo_pesquisa}%')
        ))

    # 4. Aplicar Filtro de "POSTS SALVOS" (se existir)
    if filtro == 'salvos':
        query = query.join(PostSalvo).filter(PostSalvo.user_id == current_user.id)

    # 5. Aplicar ORDENAÇÃO
    if ordenar_por == 'relevancia':
        # Ordena pela contagem de 'likes' (PostLike)
        query = query.outerjoin(PostLike).group_by(Topico.id).order_by(desc(func.count(PostLike.id)))
    else:
        # Padrão: ordena por 'mais recente'
        query = query.order_by(desc(Topico.criado_em))

    # 6. Executar a consulta
    topicos = query.all()
    
    # --- (Lógica de likes/salvos do usuário - igual a antes) ---
    likes_usuario = [like.topico_id for like in PostLike.query.filter_by(user_id=current_user.id).all()]
    salvos_usuario = [salvo.topico_id for salvo in PostSalvo.query.filter_by(user_id=current_user.id).all()]

    return render_template(
        'tela_foruns.html', 
        topicos=topicos,
        likes_usuario=likes_usuario,
        salvos_usuario=salvos_usuario,
        # 7. Envia os filtros de volta para o HTML "lembrar" as seleções
        termo_pesquisado=termo_pesquisa,
        ordenacao_selecionada=ordenar_por,
        filtro_selecionado=filtro
    )


@main_bp.route('/forum/postar', methods=['POST'])
@login_required
def criar_post():
    """
    Rota para o modal "Novo Post".
    """
    conteudo = request.form.get('conteudo_post')
    if not conteudo:
        flash('O post não pode ficar vazio.', 'warning')
        return redirect(url_for('main.tela_foruns'))

    linhas = conteudo.split('\n', 1)
    titulo = linhas[0].strip()[:150]
    if not titulo:
        titulo = "Novo Post"

    novo_topico = Topico(
        titulo=titulo,
        conteudo=conteudo,
        autor_id=current_user.id
    )
    db.session.add(novo_topico)
    db.session.commit()
    
    flash('Post criado com sucesso!', 'success')
    return redirect(url_for('main.tela_foruns'))

@main_bp.route('/forum/<int:topico_id>/comentar', methods=['POST'])
@login_required
def comentar_post(topico_id):
    """
    ATUALIZADO: Agora também cria uma notificação.
    """
    conteudo = request.form.get('conteudo_comentario')
    topico = Topico.query.get_or_404(topico_id)

    if not conteudo:
        flash('O comentário não pode ficar vazio.', 'warning')
        return redirect(url_for('main.tela_foruns'))

    nova_resposta = Resposta(
        conteudo=conteudo,
        topico_id=topico.id,
        autor_id=current_user.id
    )
    db.session.add(nova_resposta)
    
    # --- LÓGICA DE NOTIFICAÇÃO ADICIONADA ---
    try:
        # Só notifica se quem comentou NÃO for o dono do post
        if topico.autor_id != current_user.id:
            nova_notificacao = Notificacao(
                mensagem=f"{current_user.name} comentou no seu post: \"{topico.titulo}\"",
                link_url=url_for('main.tela_foruns'), # (Idealmente, um link para o post)
                usuario_id=topico.autor_id # Envia a notificação para o autor do tópico
            )
            db.session.add(nova_notificacao)
        
        db.session.commit() # Salva o comentário e a notificação
        flash('Comentário enviado!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao salvar comentário ou notificação: {e}', 'danger')
    
    return redirect(url_for('main.tela_foruns'))

@main_bp.route('/forum/<int:topico_id>/like', methods=['POST'])
@login_required
def like_post(topico_id):
    """
    Rota para o botão "Relevante".
    """
    topico = Topico.query.get_or_404(topico_id)
    like_existente = PostLike.query.filter_by(
        user_id=current_user.id,
        topico_id=topico.id
    ).first()

    if like_existente:
        db.session.delete(like_existente)
        flash('Post desmarcado como relevante.', 'info')
    else:
        novo_like = PostLike(user_id=current_user.id, topico_id=topico.id)
        db.session.add(novo_like)
        flash('Post marcado como relevante!', 'success')
    
    db.session.commit()
    return redirect(request.referrer or url_for('main.tela_foruns')) # Volta para a pág anterior

@main_bp.route('/forum/<int:topico_id>/salvar', methods=['POST'])
@login_required
def salvar_post(topico_id):
    """
    Rota para o botão "Salvar Post".
    """
    topico = Topico.query.get_or_404(topico_id)
    save_existente = PostSalvo.query.filter_by(
        user_id=current_user.id,
        topico_id=topico.id
    ).first()

    if save_existente:
        db.session.delete(save_existente)
        flash('Post removido dos salvos.', 'info')
    else:
        novo_salvo = PostSalvo(user_id=current_user.id, topico_id=topico.id)
        db.session.add(novo_salvo)
        flash('Post salvo com sucesso!', 'success')
    
    db.session.commit()
    return redirect(request.referrer or url_for('main.tela_foruns')) # Volta para a pág anterior

@main_bp.route('/forum/<int:topico_id>/excluir', methods=['POST'])
@login_required
def excluir_post(topico_id):
    """
    Rota para o Admin excluir posts.
    """
    topico = Topico.query.get_or_404(topico_id)
    if not current_user.is_admin and topico.autor_id != current_user.id:
        flash('Você não tem permissão para fazer isso.', 'danger')
        return redirect(url_for('main.tela_foruns'))
        
    db.session.delete(topico)
    db.session.commit()
    
    flash('Tópico excluído.', 'warning')
    return redirect(url_for('main.tela_foruns'))

@main_bp.route('/forum/<int:topico_id>/denunciar', methods=['POST'])
@login_required
def denunciar_post(topico_id):
    """
    NOVO: Rota para receber a denúncia de um post.
    """
    topico = Topico.query.get_or_404(topico_id)
    descricao_denuncia = request.form.get('descricao')

    if not descricao_denuncia:
        flash('Você precisa fornecer um motivo para a denúncia.', 'danger')
        return redirect(url_for('main.tela_foruns'))

    # Cria uma descrição mais completa para o admin
    descricao_completa = f"Denúncia contra o Tópico ID #{topico.id} (Título: {topico.titulo})\n"
    descricao_completa += f"Autor do Tópico: {topico.autor.name}\n\n"
    descricao_completa += f"Motivo: {descricao_denuncia}"

    nova_denuncia = Denuncia(
        tipo_denuncia="Denúncia de Post no Fórum",
        descricao=descricao_completa,
        denunciante_id=current_user.id # Registra quem denunciou
    )

    try:
        db.session.add(nova_denuncia)
        db.session.commit()
        flash('Denúncia enviada com sucesso. A administração irá analisar.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ocorreu um erro ao enviar sua denúncia: {e}', 'danger')

    return redirect(url_for('main.tela_foruns'))

# ------------------------------------------------------------
# ROTAS RESTANTES (PLACEHOLDERS E OUTRAS)
# ------------------------------------------------------------
    
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
        perfil = current_user.perfil
        if not perfil:
            perfil = Perfil(user_id=current_user.id)
            db.session.add(perfil)
        form.populate_obj(perfil)
        try:
            db.session.commit()
            flash('Perfil atualizado com sucesso!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar o perfil: {e}', 'danger')
        return redirect(url_for('main.tela_perfil'))

    meus_posts = Topico.query.filter_by(autor_id=current_user.id).order_by(Topico.criado_em.desc()).all()
    meus_materiais = Material.query.filter_by(autor_id=current_user.id).order_by(Material.data_upload.desc()).all()
    
    # Atualizado: Busca os Tópicos salvos, não os objetos PostSalvo
    meus_salvos_query = Topico.query.join(PostSalvo).filter(PostSalvo.user_id == current_user.id)
    meus_salvos = meus_salvos_query.order_by(desc(PostSalvo.id)).all()

    return render_template(
        'tela_perfil.html', 
        form=form,
        posts=meus_posts,
        materiais=meus_materiais,
        salvos=meus_salvos # Envia a lista de Tópicos salvos
    )

@main_bp.route('/denuncias')
@login_required
def tela_denuncias():
    if not current_user.is_admin:
        flash('Você não tem permissão para acessar esta página.', 'danger')
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

# --- ROTAS DE AÇÃO PARA DENÚNCIAS ---

@main_bp.route('/denuncia/resolver/<int:denuncia_id>', methods=['POST'])
@login_required
def resolver_denuncia(denuncia_id):
    if not current_user.is_admin:
        return redirect(url_for('main.tela_inicial'))
    denuncia = Denuncia.query.get_or_404(denuncia_id)
    denuncia.status = 'Resolvida'
    try:
        db.session.commit()
        flash('Denúncia marcada como resolvida.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao atualizar denúncia: {e}', 'danger')
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
        flash('Denúncia excluída com sucesso.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir denúncia: {e}', 'danger')
    return redirect(url_for('main.tela_denuncias'))

# ------------------------------------------------------------
# TELA DE MATERIAIS
# ------------------------------------------------------------

@main_bp.route('/materiais')
@login_required
def tela_materiais():
    categoria_filtro = request.args.get('categoria')
    termo_pesquisa = request.args.get('q')
    query_base = Material.query
    
    if categoria_filtro:
        query_base = query_base.filter(Material.categoria == categoria_filtro)
    
    materiais_query = query_base.order_by(Material.categoria, Material.titulo).all()

    if termo_pesquisa:
        resultados_fuzzy = []
        for material in materiais_query:
            texto_completo = f"{material.titulo} {material.descricao or ''}"
            score = fuzz.partial_ratio(termo_pesquisa.lower(), texto_completo.lower()) 
            if score > 60:
                resultados_fuzzy.append((material, score))
        resultados_fuzzy.sort(key=lambda x: x[1], reverse=True)
        materiais_query = [material for material, score in resultados_fuzzy]

    materiais_agrupados = {}
    for material in materiais_query:
        categoria = material.categoria if material.categoria else "Geral"
        if categoria not in materiais_agrupados:
            materiais_agrupados[categoria] = []
        materiais_agrupados[categoria].append(material)
    
    categorias_query = db.session.query(Material.categoria).distinct().order_by(Material.categoria)
    categorias = [c[0] for c in categorias_query if c[0]]

    return render_template(
        'tela_materiais.html', 
        materiais_agrupados=materiais_agrupados,
        categorias=categorias,
        categoria_selecionada=categoria_filtro,
        termo_pesquisado=termo_pesquisa
    )

# ------------------------------------------------------------
# ADICIONAR MATERIAL
# ------------------------------------------------------------

@main_bp.route('/materiais/adicionar', methods=['POST'])
@login_required
def adicionar_material():
    if request.method == 'POST':
        try:
            titulo = request.form.get('materialTitulo')
            descricao = request.form.get('materialDescricao')
            arquivo = request.files.get('materialArquivo')
            
            categoria_nova = request.form.get('materialCategoriaNova')
            if categoria_nova:
                categoria = categoria_nova.strip().capitalize()
            else:
                categoria = request.form.get('materialCategoriaExistente')
            
            if not titulo or not arquivo or not arquivo.filename:
                flash('Erro: Título e Arquivo são obrigatórios.', 'danger')
                return redirect(url_for('main.tela_materiais'))
            if not categoria:
                flash('Erro: Por favor, selecione ou crie uma categoria.', 'danger')
                return redirect(url_for('main.tela_materiais'))

            filename = secure_filename(arquivo.filename)
            upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            
            if os.path.exists(upload_path):
                flash('Atenção: Um arquivo com este nome já existe. Renomeie e tente novamente.', 'warning')
                return redirect(url_for('main.tela_materiais'))
                
            arquivo.save(upload_path)
            
            db_path = os.path.join('static', 'uploads', filename).replace(os.path.sep, '/')

            # CORRIGIDO: Usa o ID do usuário logado (current_user.id)
            novo_material = Material(
                titulo=titulo,
                descricao=descricao,
                arquivo_path=db_path,
                categoria=categoria,
                autor_id=current_user.id 
            )
            
            db.session.add(novo_material)
            db.session.commit()
            flash('Material adicionado com sucesso!', 'success')
        
        except Exception as e:
            db.session.rollback()
            flash(f'Erro interno ao salvar o material: {e}', 'danger')

    return redirect(url_for('main.tela_materiais'))

# ------------------------------------------------------------
# DOWNLOAD MATERIAL
# ------------------------------------------------------------

@main_bp.route('/materiais/download/<int:material_id>')
@login_required
def download_material(material_id):
    material = Material.query.get_or_404(material_id)
    try:
        directory = os.path.join(current_app.root_path, 'static', 'uploads')
        filename = os.path.basename(material.arquivo_path)
        return send_from_directory(directory, filename, as_attachment=False, conditional=True)
    except FileNotFoundError:
        flash('Arquivo não encontrado no servidor. Pode ter sido removido.', 'danger')
        return redirect(url_for('main.tela_materiais'))

# ------------------------------------------------------------
# EXCLUIR MATERIAL
# ------------------------------------------------------------

@main_bp.route('/materiais/excluir/<int:material_id>', methods=['POST'])
@login_required
def excluir_material(material_id):
    material = Material.query.get_or_404(material_id)
    
    # CORRIGIDO: Só admin ou o dono podem excluir
    if not current_user.is_admin and material.autor_id != current_user.id:
        flash('Você não tem permissão para excluir este material.', 'danger')
        return redirect(url_for('main.tela_materiais'))

    try:
        arquivo_path_abs = os.path.join(current_app.root_path, material.arquivo_path)
        if os.path.exists(arquivo_path_abs):
            os.remove(arquivo_path_abs)
        db.session.delete(material)
        db.session.commit()
        flash('Material excluído com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir material: {e}', 'danger')
    return redirect(url_for('main.tela_materiais'))

# ------------------------------------------------------------
# SUPORTE
# ------------------------------------------------------------

@main_bp.route('/suporte', methods=['GET', 'POST'])
@login_required
def suporte():
    if request.method == 'POST':
        assunto = request.form.get('title')
        descricao = request.form.get('description')

        if not descricao:
            flash('Erro: A descrição da denúncia é obrigatória.', 'danger')
            return redirect(url_for('main.suporte'))

        descricao_completa = f"Assunto: {assunto}\n\n{descricao}" if assunto else descricao

        nova_denuncia = Denuncia(
            tipo_denuncia="Denúncia via Página de Suporte",
            descricao=descricao_completa,
            denunciante_id=current_user.id # CORRIGIDO: Registra quem denunciou
        )

        try:
            db.session.add(nova_denuncia)
            db.session.commit()
            flash('Sua denúncia foi enviada.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Ocorreu um erro ao enviar sua denúncia: {e}', 'danger')

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

@main_bp.route('/tela_admin')
@login_required
def tela_admin():
    if current_user.is_admin:
        return render_template('tela_admin.html')
    
    return redirect(request.referrer)


