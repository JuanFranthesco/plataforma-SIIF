from flask import Blueprint, request, jsonify, render_template, current_app
from app.models import Noticia, Evento, db, User, Material, Comentario
from datetime import datetime, timezone
import os
from werkzeug.utils import secure_filename
from flask_login import login_required, current_user
import bleach

api = Blueprint("api", __name__)
from typing import Tuple

UPLOAD_FOLDER = "app/static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ===================================================================
# HELPER FUNCTIONS
# ===================================================================

def validate_comment_text(texto: str) -> Tuple[bool, str]:
    """Valida texto do comentário. Retorna (é_válido, mensagem_erro)."""
    texto = texto.strip()
    
    if not texto:
        return False, "O comentário não pode estar vazio"
    
    if len(texto) > 500:
        return False, "O comentário não pode ter mais de 500 caracteres"
    
    return True, ""



@api.route("/api/noticias", methods=["POST"])
def criar_noticia():
    titulo = request.form.get("titulo")
    conteudo = request.form.get("conteudo")
    campus = request.form.get("campus")
    categoria = request.form.get("categoria")
    link_externo = request.form.get("link_externo")

    imagem = request.files.get("imagem")
    arquivo = request.files.get("arquivo")

    imagem_url = None
    arquivo_url = None

    if imagem:
        nome_imagem = secure_filename(imagem.filename)
        caminho = os.path.join(UPLOAD_FOLDER, nome_imagem)
        imagem.save(caminho)
        imagem_url = f"/static/uploads/{nome_imagem}"

    if arquivo:
        nome_arquivo = secure_filename(arquivo.filename)
        caminho = os.path.join(UPLOAD_FOLDER, nome_arquivo)
        arquivo.save(caminho)
        arquivo_url = f"/static/uploads/{nome_arquivo}"

    noticia = Noticia(
        titulo=titulo,
        conteudo=conteudo,
        campus=campus,
        categoria=categoria,
        link_externo=link_externo,
        imagem_url=imagem_url,
        arquivo_url=arquivo_url,
        data_postagem=datetime.now(timezone.utc),
        autor_id=1
    )

    db.session.add(noticia)
    db.session.commit()

    return jsonify({"msg": "Notícia criada com sucesso!"}), 201


# Para que corresponda ao JavaScript
@api.route("/api/noticias", methods=["GET"])
def listar_noticias():
    noticias = Noticia.query.order_by(Noticia.data_postagem.desc()).all()

    resultado = []
    for n in noticias:
        resultado.append({
            "id": n.id,
            "titulo": n.titulo,
            "conteudo": n.conteudo,
            "imagem_url": n.imagem_url,
            "arquivo_url": n.arquivo_url,
            "link_externo": n.link_externo,
            "campus": n.campus,
            "categoria": n.categoria,
            "data_postagem": n.data_postagem.isoformat(),
            "autor_id": n.autor_id
        })


    return jsonify(resultado)


@api.route("/api/eventos", methods=["GET"])
def listar_eventos():
    try:
        # Busca do modelo Evento que você definiu
        eventos = Evento.query.order_by(Evento.data_hora_inicio.desc()).all() 

        resultado = []
        for e in eventos:
            resultado.append({
                "id": e.id,
                "titulo": e.titulo,
                "descricao": e.descricao,
                "data_hora_inicio": e.data_hora_inicio.isoformat()
            })
        return jsonify(resultado)
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


# Rota POST corrigida para receber JSON e processar data ISO 8601
@api.route("/api/eventos", methods=["POST"])
def criar_evento():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"erro": "Nenhum dado JSON fornecido."}), 400

        titulo = data.get("titulo")
        # O frontend envia 'data_hora_inicio' e não 'data'
        data_hora_inicio_str = data.get("data_hora_inicio") 
        link = data.get("link") 
        
        # O campo 'descricao' não é enviado pelo frontend.
        descricao = titulo # Usamos o título como fallback para evitar que o modelo falhe se 'descricao' for obrigatório.

        if not titulo or not data_hora_inicio_str:
             return jsonify({"erro": "Título e data são campos obrigatórios."}), 400

        # Converte a string ISO 8601 completa (ex: 2025-11-21T17:15:04.000Z) para objeto datetime
        try:
            data_obj = datetime.fromisoformat(data_hora_inicio_str)
        except ValueError:
            return jsonify({"erro": "Formato de data/hora inválido. Esperado ISO 8601."}), 400

        novo_evento = Evento(
            titulo=titulo,
            descricao=descricao, 
            data_hora_inicio=data_obj,
            organizador_id=1 
        )
        db.session.add(novo_evento)
        db.session.commit()
        
        return jsonify({"msg": "Evento criado com sucesso!", "link": link}), 201

    except Exception as e:
        db.session.rollback()
        # Retorna erro 400 para erros relacionados ao cliente (dados)
        print(f"Erro inesperado ao criar evento: {e}")
        return jsonify({"erro": f"Erro ao processar o evento: {str(e)}"}), 400


# ROTA PARA EXCLUIR NOTÍCIA
@api.route("/api/noticias/<int:noticia_id>", methods=["DELETE"])
def excluir_noticia(noticia_id):
    # TODO: Adicionar verificação de admin (ex: if not current_user.is_admin: return jsonify(...), 403)
    
    noticia = Noticia.query.get_or_404(noticia_id)
    
    try:
        # 1. Excluir arquivos físicos (imagem e anexo)
        if noticia.imagem_url:
            try:
                # Converte a URL (ex: /static/uploads/img.png) para um caminho de arquivo (ex: app/static/uploads/img.png)
                caminho_img = os.path.join(current_app.root_path, noticia.imagem_url.lstrip('/'))
                if os.path.exists(caminho_img):
                    os.remove(caminho_img)
            except Exception as e:
                print(f"Erro ao excluir imagem: {e}") # Loga o erro, mas continua

        if noticia.arquivo_url:
            try:
                caminho_arq = os.path.join(current_app.root_path, noticia.arquivo_url.lstrip('/'))
                if os.path.exists(caminho_arq):
                    os.remove(caminho_arq)
            except Exception as e:
                print(f"Erro ao excluir arquivo: {e}") # Loga o erro, mas continua

        # 2. Excluir do banco de dados
        db.session.delete(noticia)
        db.session.commit()
        
        return jsonify({"msg": "Notícia excluída com sucesso!"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"erro": str(e)}), 500


# ROTA PARA EXCLUIR EVENTO
@api.route("/api/eventos/<int:evento_id>", methods=["DELETE"])
def excluir_evento(evento_id):
    # TODO: Adicionar verificação de admin
    
    evento = Evento.query.get_or_404(evento_id)
    
    try:
        db.session.delete(evento)
        db.session.commit()
        return jsonify({"msg": "Evento excluído com sucesso!"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"erro": str(e)}), 500


@api.route("/api/usuarios")
def api_usuarios():
    users = User.query.filter_by(is_admin=False).order_by(User.matricula.asc()).all()

    return {
        "usuarios": [
            {
                "id": u.id,
                "name": u.name or "",
                "matricula": u.matricula,
                "is_suspenso": u.is_suspenso(),
                "suspenso_ate": u.suspenso_ate.isoformat() if u.suspenso_ate else None,
                "motivo_suspensao": u.motivo_suspensao or None,
                "foto_url": u.foto_url or None,
                "curso": u.curso or None,
                "campus": u.campus or None
            }
            for u in users
        ]
    }

# Buscar dados completos do usuário pelo ID
@api.route("/api/usuario/<int:user_id>")
@login_required
def api_usuario(user_id):
    user = User.query.get_or_404(user_id)

    return jsonify({
        "id": user.id,
        "nome": user.name,
        "matricula": user.matricula,
        "curso": user.curso,
        "campus": user.campus,
        "foto_url": user.foto_url,
        "suspenso": user.is_suspenso(),
        "suspenso_ate": user.suspenso_ate.isoformat() if user.suspenso_ate else None,
        "motivo": user.motivo_suspensao
    })


# Suspender usuário
@api.route("/api/usuario/<int:user_id>/suspender", methods=["POST"])
@login_required
def suspender_usuario(user_id):
    user = User.query.get_or_404(user_id)

    data = request.json
    quantidade = int(data.get("quantidade"))
    unidade = data.get("unidade")
    motivo = data.get("motivo", "")

    user.suspender(quantidade, unidade, motivo)
    db.session.commit()

    return jsonify({"status": "ok"})


# ✔ Remover suspensão
@api.route("/api/usuario/<int:user_id>/remover_suspensao", methods=["POST"])
@login_required
def remover_suspensao_usuario(user_id):
    user = User.query.get_or_404(user_id)
    user.remover_suspensao()
    db.session.commit()
    return jsonify({"status": "ok"})



# ===================================================================
# API DE COMENTÁRIOS (COM SEGURANÇA XSS E RATE LIMIT)
# ===================================================================

@api.route("/api/materiais/<int:material_id>/comentarios", methods=["GET"])
def listar_comentarios(material_id: int):
    """Lista todos os comentários de um material (ordenados do mais recente)."""
    try:
        material = Material.query.get_or_404(material_id)
        comentarios = (Comentario.query
                      .filter_by(material_id=material_id)
                      .order_by(Comentario.data_criacao.desc())
                      .all())
        
        resultado = []
        for c in comentarios:
            resultado.append({
                "id": c.id,
                "texto": c.texto,
                "data_criacao": c.data_criacao.isoformat(),
                "autor": {
                    "id": c.autor.id,
                    "name": c.autor.name or "Usuário",
                    "foto_url": c.autor.foto_url or "/static/img/default-avatar.png"
                }
            })
        
        return jsonify(resultado), 200
    
    except Exception as e:
        return jsonify({"erro": f"Erro ao carregar comentários: {str(e)}"}), 500


@api.route("/api/materiais/<int:material_id>/comentarios", methods=["POST"])
@login_required
def criar_comentario(material_id: int):
    """
    Cria um novo comentário em um material.
    Segurança:
    - Anti-XSS: Remove todas as tags HTML usando bleach
    - Anti-Spam: Bloqueia se o último comentário foi há menos de 30 segundos
    """
    try:
        # Validação do material
        material = Material.query.get_or_404(material_id)
        
        # Pega o texto do comentário
        data = request.get_json()
        if not data:
            return jsonify({"erro": "Nenhum dado fornecido"}), 400
        
        texto = data.get("texto", "").strip()
        
        # Validação de conteúdo usando helper
        valido, mensagem_erro = validate_comment_text(texto)
        if not valido:
            return jsonify({"erro": mensagem_erro}), 400
        
        # Anti-spam: rate limit manual
        ultimo_comentario = (Comentario.query
                            .filter_by(autor_id=current_user.id)
                            .order_by(Comentario.data_criacao.desc())
                            .first())
        
        if ultimo_comentario:
            tempo_decorrido = (datetime.now(timezone.utc) - ultimo_comentario.data_criacao).total_seconds()
            if tempo_decorrido < 30:
                tempo_restante = int(30 - tempo_decorrido)
                return jsonify({
                    "erro": f"Aguarde {tempo_restante} segundos antes de comentar novamente"
                }), 429
        
        # Anti-XSS: sanitização
        texto_limpo = bleach.clean(texto, tags=[], strip=True)
        
        # Cria o comentário
        novo_comentario = Comentario(
            texto=texto_limpo,
            autor_id=current_user.id,
            material_id=material_id
        )
        
        db.session.add(novo_comentario)
        db.session.commit()
        
        # Retorna o comentário criado
        return jsonify({
            "id": novo_comentario.id,
            "texto": novo_comentario.texto,
            "data_criacao": novo_comentario.data_criacao.isoformat(),
            "autor": {
                "id": current_user.id,
                "name": current_user.name or "Usuário",
                "foto_url": current_user.foto_url or "/static/img/default-avatar.png"
            }
        }), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({"erro": f"Erro ao criar comentário: {str(e)}"}), 500


