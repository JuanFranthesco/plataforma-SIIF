from flask import render_template, request, redirect, url_for, flash, current_app, send_from_directory, Blueprint
from flask_login import login_required, current_user
from sqlalchemy import or_
from werkzeug.utils import secure_filename
import os
import datetime
from thefuzz import fuzz
from app.models import Material, User, FAQ, Denuncia, Noticia, Evento, Perfil
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
def tela_inicial():
    """
    Tela inicial com dados reais do banco:
    - Últimas notícias
    - Próximos eventos
    """

    # -------------------------------
    # Buscar notícias (últimas 4)
    # -------------------------------
    noticias = Noticia.query.order_by(Noticia.data_postagem.desc()).limit(4).all()

    # -------------------------------
    # Buscar eventos futuros
    # -------------------------------
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
# PLACEHOLDERS (Evita erros de url_for até as telas existirem)
# ------------------------------------------------------------

@main_bp.route('/forum')
def tela_foruns():
    return render_template('tela_foruns.html')

@main_bp.route('/divulgacao')
def tela_divulgacao():
    return render_template('tela_divulgacao.html')

@main_bp.route('/mapa')
def tela_mapa():
    return render_template('tela_mapa.html')

@main_bp.route('/perfil', methods=['GET', 'POST'])
@login_required  # <-- Protege a página, exigindo login
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
        return redirect(url_for('main.tela_perfil'))'
    return render_template('tela_perfil.html', form=form)

@main_bp.route('/denuncias')
def tela_denuncias():
    return render_template('tela_denuncias.html')

# ------------------------------------------------------------
# TELA DE MATERIAIS
# ------------------------------------------------------------

@main_bp.route('/materiais')
def tela_materiais():
    """Exibe os materiais e aplica filtros."""

    categoria_filtro = request.args.get('categoria')
    termo_pesquisa = request.args.get('q')
    query_base = Material.query
    
    if categoria_filtro:
        query_base = query_base.filter(Material.categoria == categoria_filtro)
    
    # 1. Busca os materiais do DB (filtrados por categoria, se houver)
    materiais_query = query_base.order_by(Material.categoria, Material.titulo).all()

    # 2. Se houver pesquisa, filtra a lista 'materiais_query' em Python
    if termo_pesquisa:
        resultados_fuzzy = [] #o fuzzy é para n precisar ficar pesquisando o exato nome do arquivo. melhor para UX
        
        for material in materiais_query:
            texto_completo = f"{material.titulo} {material.descricao or ''}"
            score = fuzz.partial_ratio(termo_pesquisa.lower(), texto_completo.lower()) 
            if score > 60:
                resultados_fuzzy.append((material, score))

        resultados_fuzzy.sort(key=lambda x: x[1], reverse=True)
        
        # 3. Substitui a lista original pela lista filtrada e ordenada
        materiais_query = [material for material, score in resultados_fuzzy]

    # A LINHA DUPLICADA QUE ESTAVA AQUI FOI REMOVIDA

    # 4. Agrupa os resultados (sejam eles filtrados ou não)
    materiais_agrupados = {}
    for material in materiais_query:
        categoria = material.categoria if material.categoria else "Geral"
        if categoria not in materiais_agrupados:
            materiais_agrupados[categoria] = []
        materiais_agrupados[categoria].append(material)
    
    #busca todas as categorias únicas que existem no banco
    categorias_query = db.session.query(Material.categoria).distinct().order_by(Material.categoria)
    categorias = [c[0] for c in categorias_query if c[0]] # Lista limpa de nomes

    return render_template(
        'tela_materiais.html', 
        materiais_agrupados=materiais_agrupados,
        categorias=categorias,
        categoria_selecionada=categoria_filtro, #para o filtro 'lembrar' a seleção
        termo_pesquisado=termo_pesquisa #para a parte de pesquisa
    )

# ------------------------------------------------------------
# ADICIONAR MATERIAL
# ------------------------------------------------------------

@main_bp.route('/materiais/adicionar', methods=['POST'])
def adicionar_material():
    """
    Rota que recebe os dados do modal "Adicionar Material".
    """
    if request.method == 'POST':
        try:
            #pegar dados do formulário
            titulo = request.form.get('materialTitulo')
            descricao = request.form.get('materialDescricao')
            arquivo = request.files.get('materialArquivo')
            
            #lógica de Categoria (prioriza a nova)
            categoria_nova = request.form.get('materialCategoriaNova')
            if categoria_nova:
                categoria = categoria_nova.strip().capitalize()
            else:
                categoria = request.form.get('materialCategoriaExistente')
            
            #validação
            if not titulo or not arquivo or not arquivo.filename:
                flash('Erro: Título e Arquivo são obrigatórios.', 'danger')
                return redirect(url_for('main.tela_materiais'))

            if not categoria:
                flash('Erro: Por favor, selecione ou crie uma categoria.', 'danger')
                return redirect(url_for('main.tela_materiais'))

            #salvar o arquivo físico
            filename = secure_filename(arquivo.filename)
            upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            
            if os.path.exists(upload_path):
                flash('Atenção: Um arquivo com este nome já existe. Renomeie e tente novamente.', 'warning')
                return redirect(url_for('main.tela_materiais'))
                
            arquivo.save(upload_path)
            
            #salvar no Banco de Dados
            db_path = os.path.join('static', 'uploads', filename).replace(os.path.sep, '/')

            #AVISO: to usando 'autor_id=1' como placeholder.
            #vc precisa trocar isso pelo ID do usuário logado (ex: current_user.id) 
            #quando implementar a autenticação.
            
            #garante que o usuário autor (ID 1) exista para teste
            autor = User.query.get(1)
            if not autor:
                autor = User(id=1, matricula="00000001", email="admin@siif.com", is_admin=True)
                db.session.add(autor)

            novo_material = Material(
                titulo=titulo,
                descricao=descricao,
                arquivo_path=db_path,
                categoria=categoria,
                autor_id=autor.id 
            )
            
            db.session.add(novo_material)
            db.session.commit()
            
            flash('Material adicionado com sucesso!', 'success')
        
        except Exception as e:
            db.session.rollback() #desfaz qualquer mudança no banco se der erro
            flash(f'Erro interno ao salvar o material: {e}', 'danger')

    return redirect(url_for('main.tela_materiais'))

# ------------------------------------------------------------
# DOWNLOAD MATERIAL
# ------------------------------------------------------------

@main_bp.route('/materiais/download/<int:material_id>')
def download_material(material_id):
    """
    Rota para "Acessar" (fazer download ou exibir) um arquivo.
    """
    material = Material.query.get_or_404(material_id)
    
    try:
        #material.arquivo_path é 'static/uploads/meu_arquivo.pdf'
        #precisamos do diretório (relativo à pasta 'app') e do nome do arquivo
        directory = os.path.join(current_app.root_path, 'static', 'uploads')
        filename = os.path.basename(material.arquivo_path)
        
        return send_from_directory(directory, filename, as_attachment=False, conditional=True)
        # send_from_directory é a forma segura de servir arquivos
        # as_attachment=False tenta abrir o arquivo no navegador (ex: PDFs)
        
    except FileNotFoundError:
        flash('Arquivo não encontrado no servidor. Pode ter sido removido.', 'danger')
        return redirect(url_for('main.tela_materiais'))

# ------------------------------------------------------------
# EXCLUIR MATERIAL
# ------------------------------------------------------------

@main_bp.route('/materiais/excluir/<int:material_id>', methods=['POST'])
def excluir_material(material_id):
    """
    Rota para o botão de excluir (lixeira).
    (Futuramente, adicionar verificação de admin)
    """
    # TODO: Adicionar verificação de admin (ex: if not current_user.is_admin: ...)
    
    material = Material.query.get_or_404(material_id)
    
    try:
        #excluir o arquivo físico do disco
        arquivo_path_abs = os.path.join(current_app.root_path, material.arquivo_path)
        if os.path.exists(arquivo_path_abs):
            os.remove(arquivo_path_abs)
            
        #excluir a referência do banco de dados
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
            denunciante_id=None
        )

        try:
            db.session.add(nova_denuncia)
            db.session.commit()
            flash('Sua denúncia foi enviada anonimamente.', 'success')
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
