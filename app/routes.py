
from flask import Blueprint, render_template

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
@main_bp.route('/index')
def index():
    
    return "<h1>Projeto SIIF está no AR!</h1>"