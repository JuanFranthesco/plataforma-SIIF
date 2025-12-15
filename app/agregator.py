import requests
from bs4 import BeautifulSoup
import datetime
from datetime import timedelta
import re

# Importações do seu projeto
from app import create_app
from app.extensions import db
from app.models import NoticiaAgregada

# URL da página de notícias da Reitoria
URL_ALVO = "https://portal.ifrn.edu.br/campus/reitoria/noticias/"
DOMINIO = "https://portal.ifrn.edu.br"


def interpretar_data_relativa(texto_data):
    agora = datetime.datetime.now(datetime.timezone.utc)

    if not texto_data:
        return agora

    try:
        texto = texto_data.lower()
        delta = timedelta()

        # Procura por "X dias"
        dias_match = re.search(r'(\d+)\s*dias?', texto)
        if dias_match:
            delta += timedelta(days=int(dias_match.group(1)))

        # Procura por "X horas"
        horas_match = re.search(r'(\d+)\s*horas?', texto)
        if horas_match:
            delta += timedelta(hours=int(horas_match.group(1)))

        # Procura por "X minutos"
        minutos_match = re.search(r'(\d+)\s*minutos?', texto)
        if minutos_match:
            delta += timedelta(minutes=int(minutos_match.group(1)))

        # Se encontrou algum tempo, subtrai do momento atual
        if delta.total_seconds() > 0:
            return agora - delta

        return agora

    except Exception:
        return agora


def buscar_noticias_ifrn():
    print(f"--- Iniciando Scraping em: {URL_ALVO} ---")

    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/91.0.4472.124 Safari/537.36'
        )
    }

    try:
        response = requests.get(URL_ALVO, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"ERRO DE CONEXÃO: {e}")
        return

    soup = BeautifulSoup(response.content, 'html.parser')

    # O link (<a>) possui a classe 'grid-item'
    itens_noticia = soup.select('a.grid-item')

    if not itens_noticia:
        print("AVISO: Nenhuma notícia encontrada com a classe 'grid-item'.")
        return

    novas_count = 0

    # Processa as 10 primeiras notícias
    for item in itens_noticia[:10]:
        try:
            # 1. LINK
            link_relativo = item.get('href')
            if not link_relativo:
                continue

            if link_relativo.startswith('/'):
                link_final = DOMINIO + link_relativo
            else:
                link_final = link_relativo

            # 2. VERIFICA SE JÁ EXISTE
            if NoticiaAgregada.query.filter_by(link_externo=link_final).first():
                continue

            # 3. TÍTULO
            tag_titulo = item.select_one('h3')
            titulo = tag_titulo.text.strip() if tag_titulo else "Sem Título"

            # 4. SUBTÍTULO
            tag_subtitulo = item.select_one('.subtitulo')
            conteudo = tag_subtitulo.text.strip() if tag_subtitulo else ""

            # 5. DATA
            tag_data = item.select_one('.date')
            data_texto = tag_data.text.strip() if tag_data else ""
            data_publicacao = interpretar_data_relativa(data_texto)

            # 6. IMAGEM
            tag_img = item.select_one('img')
            imagem_url = None
            if tag_img and tag_img.get('src'):
                src = tag_img.get('src')
                imagem_url = DOMINIO + src if src.startswith('/') else src

            # 7. SALVAR
            nova_noticia = NoticiaAgregada(
                titulo=titulo,
                conteudo=conteudo,
                link_externo=link_final,
                data_publicacao=data_publicacao,
                imagem_url=imagem_url,
                campus="Reitoria",
                categoria="Notícia Portal"
            )

            db.session.add(nova_noticia)
            novas_count += 1
            print(f"[NOVA] {titulo}")

        except Exception as e:
            print(f"Erro ao processar item: {e}")
            continue

    if novas_count > 0:
        db.session.commit()
        print(f"\n--- SUCESSO! {novas_count} notícias novas salvas. ---")
    else:
        print("\n--- Nenhuma notícia nova encontrada. ---")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        buscar_noticias_ifrn()
