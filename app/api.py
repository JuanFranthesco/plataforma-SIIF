from flask import Blueprint, request, jsonify, render_template, current_app
from app.models import Noticia, Evento, db 
from datetime import datetime, timezone
import os
from werkzeug.utils import secure_filename

api = Blueprint("api", __name__)

UPLOAD_FOLDER = "app/static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


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


 

# ... (suas outras rotas) ...

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


        # No topo do api.py, adicione o import de datetime




@api.route("/api/eventos", methods=["POST"])
def criar_evento():
    try:
        titulo = request.form.get("titulo")
        data_str = request.form.get("data") # O JS vai mandar 'titulo', 'data' e 'link'
        link = request.form.get("link")

        # ATENÇÃO: Isso é uma conversão simples. 
        # Numa app real, use um seletor de data (datepicker)
        try:
            data_obj = datetime.strptime(data_str, "%d/%m")
            data_obj = data_obj.replace(year=datetime.now().year, tzinfo=timezone.utc)
        except ValueError:
            data_obj = datetime.now(timezone.utc) # Fallback

        novo_evento = Evento(
            titulo=titulo,
            descricao=request.form.get("descricao", titulo), # Modelo exige descrição
            data_hora_inicio=data_obj,
            organizador_id=1 # Mude para 'current_user.id' quando tiver login
        )
        db.session.add(novo_evento)
        db.session.commit()
        return jsonify({"msg": "Evento criado com sucesso!"}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"erro": str(e)}), 400



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

