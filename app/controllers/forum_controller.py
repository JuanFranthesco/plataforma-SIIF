# forum_controller.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.extensions import db
from app.models import Topico, Resposta, User
from functools import wraps

forum_bp = Blueprint("forum", __name__)

# Decorator para exigir login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Você precisa estar logado para acessar essa página.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated_function

# Página principal do fórum
@forum_bp.route("/foruns")
@login_required
def tela_foruns():
    topicos = Topico.query.order_by(Topico.created_at.desc()).all()
    return render_template("tela_foruns.html", topicos=topicos, User=User)

# Criar novo post
@forum_bp.route("/foruns/novo", methods=["POST"])
@login_required
def criar_topico():
    conteudo = request.form.get("conteudo")
    if not conteudo:
        flash("O post não pode ficar vazio.", "warning")
        return redirect(url_for("forum.tela_foruns"))

    novo_topico = Topico(user_id=session["user_id"], conteudo=conteudo)
    db.session.add(novo_topico)
    db.session.commit()
    flash("Post criado com sucesso!", "success")
    return redirect(url_for("forum.tela_foruns"))

# Comentar em um post
@forum_bp.route("/foruns/<int:topico_id>/comentar", methods=["POST"])
@login_required
def comentar_topico(topico_id):
    conteudo = request.form.get("conteudo")
    if not conteudo:
        flash("O comentário não pode ficar vazio.", "warning")
        return redirect(url_for("forum.tela_foruns"))

    resposta = Resposta(user_id=session["user_id"], topico_id=topico_id, conteudo=conteudo)
    db.session.add(resposta)
    db.session.commit()
    flash("Comentário enviado!", "success")
    return redirect(url_for("forum.tela_foruns"))

# Marcar post como relevante
@forum_bp.route("/foruns/<int:topico_id>/relevante", methods=["POST"])
@login_required
def marcar_relevante(topico_id):
    topico = Topico.query.get_or_404(topico_id)
    if "liked_posts" not in session:
        session["liked_posts"] = []

    if topico_id not in session["liked_posts"]:
        topico.relevancia += 1
        session["liked_posts"].append(topico_id)
    else:
        topico.relevancia -= 1
        session["liked_posts"].remove(topico_id)

    db.session.commit()
    return redirect(url_for("forum.tela_foruns"))
