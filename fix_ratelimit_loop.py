"""
Script para corrigir o loop infinito de rate limit no SIIF
Aplica patch seguro ao arquivo __init__.py
"""

import re

TARGET_FILE = r'app/__init__.py'

# Código antigo (problemático)
OLD_CODE = '''    # Handler para erro de Rate Limit (429)
    @app.errorhandler(429)
    def ratelimit_handler(e):
        from flask import flash, redirect, request, url_for
        flash('Você atingiu o limite de requisições. Por favor, aguarde alguns minutos e tente novamente.', 'warning')
        return redirect(request.referrer or url_for('main.tela_inicial'))'''

# Código novo (corrigido)
NEW_CODE = '''    # Handler para erro de Rate Limit (429)
    @app.errorhandler(429)
    def ratelimit_handler(e):
        from flask import render_template_string
        # CRÍTICO: NÃO redirecionar! Renderizar página de erro estática.
        error_template = \'''
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Limite Atingido - SIIF</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css" rel="stylesheet">
            <style>
                body {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                .error-container {
                    background: rgba(255, 255, 255, 0.98);
                    padding: 60px;
                    border-radius: 20px;
                    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                    text-align: center;
                    max-width: 600px;
                }
                .error-code { font-size: 100px; font-weight: bold; color: #667eea; margin: 0; }
                .error-title { font-size: 24px; color: #333; margin: 20px 0; }
                .error-message { color: #666; margin-bottom: 30px; }
            </style>
        </head>
        <body>
            <div class="error-container">
                <h1 class="error-code">429</h1>
                <h2 class="error-title">Limite de Requisições Atingido</h2>
                <p class="error-message">
                    Você fez muitas requisições em um curto período de tempo.<br>
                    Por favor, aguarde alguns momentos antes de continuar.
                </p>
                <a href="{{ url_for('main.tela_inicial') }}" class="btn btn-primary btn-lg">
                    <i class="bi bi-house-door-fill me-2"></i>Voltar ao Início
                </a>
            </div>
        </body>
        </html>
        \'''
        return render_template_string(error_template), 429'''

def apply_patch():
    """Aplica o patch de correção do rate limit"""
    print("🔧 Aplicando correção de loop infinito de rate limit...")
    
    try:
        # Ler arquivo
        with open(TARGET_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Verificar se já foi aplicado
        if 'render_template_string' in content and 'CRÍTICO: NÃO redirecionar!' in content:
            print("✅ Patch já foi aplicado anteriormente!")
            return True
        
        # Verificar se o código antigo existe
        if 'return redirect(request.referrer or url_for' not in content:
            print("⚠️  Código antigo não encontrado. Arquivo pode ter sido modificado.")
            return False
        
        # Aplicar substituição
        content_new = content.replace(OLD_CODE, NEW_CODE)
        
        if content == content_new:
            print("❌ Nenhuma mudança foi feita. Verifique o código manualmente.")
            return False
        
        # Fazer backup
        backup_file = TARGET_FILE + '.backup_ratelimit'
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"💾 Backup criado: {backup_file}")
        
        # Salvar arquivo corrigido
        with open(TARGET_FILE, 'w', encoding='utf-8') as f:
            f.write(content_new)
        
        print("✅ Patch aplicado com sucesso!")
        print("\n📌 PRÓXIMOS PASSOS:")
        print("   1. Reinicie o servidor Flask")
        print("   2. Teste acessando /materiais?filtro=favoritos")
        print("   3. Verifique se não há mais loops infinitos")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao aplicar patch: {e}")
        return False

if __name__ == '__main__':
    apply_patch()
