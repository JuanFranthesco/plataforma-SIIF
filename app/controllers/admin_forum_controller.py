# app/controllers/admin_forum_controller.py
"""
Ações administrativas relacionadas ao fórum.
- validação _require_admin para permitir apenas admins
- deletar tópico, deletar resposta, promover usuário a admin
"""

from flask import redirect, url_for, flash, session
from app.extensions import db
from app.models import Topico, Resposta, User


def _require_admin():
    user_id = session.get('user_id')
    if not user_id:
        flash("Acesso negado. Faça login como administrador.", "danger")
        return False
    user = User.query.get(user_id)
    if not user or not getattr(user, "is_admin", False):
        flash("Acesso negado. Administrador apenas.", "danger")
        return False
    return True


def deletar_topico(topico_id):
    if not _require_admin():
        return redirect(url_for("main.home"))

    topico = Topico.query.get_or_404(topico_id)
    # caso exista cascade, essa linha é redundante; mantida por segurança
    Resposta.query.filter_by(topico_id=topico.id).delete()
    db.session.delete(topico)
    db.session.commit()

    flash("Tópico deletado (admin).", "warning")
    return redirect(url_for("main.forum"))


def deletar_resposta(resposta_id):
    if not _require_admin():
        return redirect(url_for("main.home"))

    resposta = Resposta.query.get_or_404(resposta_id)
    topico_id = resposta.topico_id
    db.session.delete(resposta)
    db.session.commit()
    flash("Resposta deletada (admin).", "warning")
    return redirect(url_for("main.ver_topico", id=topico_id))


def promover_usuario(user_id):
    if not _require_admin():
        return redirect(url_for("main.home"))

    user = User.query.get_or_404(user_id)
    user.is_admin = True
    db.session.commit()
    flash(f"Usuário {user.email} promovido a admin.", "success")
    return redirect(url_for("main.perfil"))
