#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script para verificar se há arquivos maliciosos no banco de dados.
Verifica especificamente por arquivos com extensões não permitidas.
"""

import sqlite3
import os

# Extensões permitidas pelo sistema
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'jpg', 'jpeg', 'png', 'mp4'}

# Conectar ao banco de dados
db_path = os.path.join(os.path.dirname(__file__), 'app', 'site.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=" * 80)
print("VERIFICAÇÃO DE SEGURANÇA - ARQUIVOS MALICIOSOS")
print("=" * 80)
print()

# Buscar todos os materiais
cursor.execute("""
    SELECT id, titulo, arquivo_path, link_externo, autor_id, data_upload 
    FROM material 
    ORDER BY data_upload DESC
""")

materiais = cursor.fetchall()

print(f"Total de materiais no banco: {len(materiais)}")
print()

# Verificar arquivos suspeitos
arquivos_suspeitos = []
arquivos_virus = []

for material in materiais:
    material_id, titulo, arquivo_path, link_externo, autor_id, data_upload = material
    
    # Se for link externo, pular
    if link_externo:
        continue
    
    # Se não tiver arquivo, pular
    if not arquivo_path:
        continue
    
    # Extrair extensão do arquivo
    if '.' in arquivo_path:
        extensao = arquivo_path.rsplit('.', 1)[1].lower()
        
        # Verificar se a extensão é permitida
        if extensao not in ALLOWED_EXTENSIONS:
            arquivos_suspeitos.append({
                'id': material_id,
                'titulo': titulo,
                'arquivo': arquivo_path,
                'extensao': extensao,
                'autor_id': autor_id,
                'data': data_upload
            })
        
        # Verificar especificamente por 'virus.exe' ou extensões executáveis
        if 'virus' in arquivo_path.lower() or extensao in ['exe', 'bat', 'cmd', 'sh', 'ps1', 'vbs', 'js']:
            arquivos_virus.append({
                'id': material_id,
                'titulo': titulo,
                'arquivo': arquivo_path,
                'extensao': extensao,
                'autor_id': autor_id,
                'data': data_upload
            })

# Exibir resultados
print("=" * 80)
print("RESULTADO DA VERIFICAÇÃO")
print("=" * 80)
print()

if arquivos_virus:
    print("[!] ALERTA CRITICO: Arquivos potencialmente maliciosos encontrados!")
    print("-" * 80)
    for arq in arquivos_virus:
        print(f"ID: {arq['id']}")
        print(f"Titulo: {arq['titulo']}")
        print(f"Arquivo: {arq['arquivo']}")
        print(f"Extensao: {arq['extensao']}")
        print(f"Autor ID: {arq['autor_id']}")
        print(f"Data: {arq['data']}")
        print("-" * 80)
else:
    print("[OK] Nenhum arquivo malicioso (virus.exe, .exe, .bat, etc.) encontrado!")
    print()

if arquivos_suspeitos:
    print()
    print("[!] Arquivos com extensoes nao permitidas encontrados:")
    print("-" * 80)
    for arq in arquivos_suspeitos:
        print(f"ID: {arq['id']}")
        print(f"Titulo: {arq['titulo']}")
        print(f"Arquivo: {arq['arquivo']}")
        print(f"Extensao: {arq['extensao']}")
        print(f"Autor ID: {arq['autor_id']}")
        print(f"Data: {arq['data']}")
        print("-" * 80)
else:
    print("[OK] Todos os arquivos no banco tem extensoes permitidas!")
    print()

# Verificar também arquivos físicos na pasta uploads
print()
print("=" * 80)
print("VERIFICAÇÃO DE ARQUIVOS FÍSICOS NA PASTA UPLOADS")
print("=" * 80)
print()

uploads_path = os.path.join(os.path.dirname(__file__), 'app', 'static', 'uploads')

if os.path.exists(uploads_path):
    arquivos_fisicos = os.listdir(uploads_path)
    arquivos_fisicos_suspeitos = []
    
    for arquivo in arquivos_fisicos:
        if '.' in arquivo:
            extensao = arquivo.rsplit('.', 1)[1].lower()
            if extensao not in ALLOWED_EXTENSIONS:
                arquivos_fisicos_suspeitos.append({
                    'nome': arquivo,
                    'extensao': extensao
                })
    
    print(f"Total de arquivos físicos: {len(arquivos_fisicos)}")
    print()
    
    if arquivos_fisicos_suspeitos:
        print("[!] Arquivos fisicos suspeitos encontrados:")
        print("-" * 80)
        for arq in arquivos_fisicos_suspeitos:
            print(f"Arquivo: {arq['nome']}")
            print(f"Extensao: {arq['extensao']}")
            print("-" * 80)
    else:
        print("[OK] Todos os arquivos fisicos tem extensoes permitidas!")
else:
    print("[!] Pasta uploads nao encontrada!")

print()
print("=" * 80)
print("CONCLUSÃO")
print("=" * 80)
print()

if not arquivos_virus and not arquivos_suspeitos and not arquivos_fisicos_suspeitos:
    print("[OK] SISTEMA SEGURO: Nenhum arquivo malicioso ou suspeito encontrado!")
    print("   A validacao de seguranca esta funcionando corretamente.")
else:
    print("[!] ATENCAO: Foram encontrados arquivos que precisam de analise.")
    print("   Verifique os detalhes acima.")

print()

conn.close()
