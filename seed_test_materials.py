from app import create_app
from app.extensions import db
from app.models import Material, User
from datetime import datetime

app = create_app()

with app.app_context():
    # 1. Tenta pegar o primeiro usuário do banco para ser o autor
    autor = User.query.first()
    
    # Se não tiver usuário, cria um temporário
    if not autor:
        print("Nenhum usuário encontrado. Criando 'Usuario Teste'...")
        autor = User(
            matricula="00000000",
            name="Usuario Teste",
            email="teste@siif.com",
            is_admin=False
        )
        autor.set_password("123456")
        db.session.add(autor)
        db.session.commit()
        print(f"Usuário criado com ID: {autor.id}")
    else:
        print(f"Usando usuário existente: {autor.name} (ID: {autor.id})")

    # 2. Criar 10 materiais de teste
    print("Criando 10 materiais de teste na categoria 'Informática'...")
    
    for i in range(1, 11):
        material = Material(
            titulo=f"Material de Teste {i} - Informática",
            descricao=f"Descrição longa para testar o layout do card número {i}. Lorem ipsum dolor sit amet.",
            arquivo_path=None, # Sem arquivo físico
            link_externo="https://google.com",
            categoria="Informática",
            autor_id=autor.id,
            download_count=i * 5, # Números variados de downloads
            data_upload=datetime.now()
        )
        db.session.add(material)

    # 3. Salvar tudo
    db.session.commit()
    print("✅ Sucesso! 10 materiais foram adicionados.")
