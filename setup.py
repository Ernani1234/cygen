"""
Arquivo de inicialização para garantir que os diretórios necessários existam.
"""

import os
import sys

def create_required_directories():
    """Cria os diretórios necessários para o funcionamento da aplicação."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Diretórios principais
    dirs = [
        os.path.join(base_dir, "logs"),
        os.path.join(base_dir, "tests"),
        os.path.join(base_dir, "config"),
        os.path.join(base_dir, "resources", "icons")
    ]
    
    # Criar diretórios
    for directory in dirs:
        os.makedirs(directory, exist_ok=True)
        print(f"Diretório criado/verificado: {directory}")

if __name__ == "__main__":
    create_required_directories()
    print("Inicialização concluída. Todos os diretórios necessários foram criados.")
    print("Execute 'python main.py' para iniciar a aplicação.")
