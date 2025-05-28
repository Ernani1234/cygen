"""
Módulo para gerenciamento de ícones e recursos visuais.
"""

import os
import base64
from tkinter import PhotoImage
import io

class IconManager:
    """
    Gerencia ícones e recursos visuais da aplicação.
    """
    
    def __init__(self):
        """
        Inicializa o gerenciador de ícones.
        """
        self.icons = {}
        self.icon_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "resources", "icons")
        
        # Criar diretório de ícones se não existir
        os.makedirs(self.icon_dir, exist_ok=True)
        
        # Carregar ícones embutidos
        self._load_embedded_icons()
    
    def get_icon(self, name, size=24):
        """
        Retorna um ícone pelo nome.
        
        Args:
            name: Nome do ícone
            size: Tamanho do ícone (16, 24, 32)
        
        Returns:
            PhotoImage: Objeto de imagem do ícone
        """
        key = f"{name}_{size}"
        
        if key in self.icons:
            return self.icons[key]
        
        # Tentar carregar do arquivo
        icon_path = os.path.join(self.icon_dir, f"{name}_{size}.png")
        if os.path.exists(icon_path):
            try:
                icon = PhotoImage(file=icon_path)
                self.icons[key] = icon
                return icon
            except Exception:
                pass
        
        # Retornar ícone padrão se não encontrado
        return self.get_default_icon(size)
    
    def get_default_icon(self, size=24):
        """
        Retorna o ícone padrão.
        
        Args:
            size: Tamanho do ícone
        
        Returns:
            PhotoImage: Objeto de imagem do ícone padrão
        """
        key = f"default_{size}"
        
        if key in self.icons:
            return self.icons[key]
        
        # Criar ícone padrão
        return None
    
    def _load_embedded_icons(self):
        """Carrega ícones embutidos no código"""
        # Ícones básicos codificados em base64
        embedded_icons = {
            # Ícone de dashboard
            "dashboard_24": "iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAYAAADgdz34AAAABmJLR0QA/wD/AP+gvaeTAAAA70lEQVRIie2UMQ6CMBSGf4w6OLkYD+DmATyDm5uJi5uTN/AQHsLZxITRzZk4mUgcNJFSWgptHYz+SfOa9vW979GXFvgDJEAOaIesJDYRMgGUgLbISmJdSIEHoIArcAQiYfQlNhLbADdN0wEHYOTa/Aysge5N1wLrPvMpcARSx9wUODnMn8DStXkGXBzmCkiGNJ8BN4e5BhZDmRfAw2GuJNYbEbADWoe5BTJX8xBYAQ+H+R1YhjDXmQBHYfQAYl/zGFhJrJK1Hhj7mG+k0Zk0aqTRzWTNi7kWXcnaCojeMc+l0VkafYHZO+ZfwQsqVD/2HFhqTAAAAABJRU5ErkJggg==",
            
            # Ícone de captura
            "capture_24": "iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAYAAADgdz34AAAABmJLR0QA/wD/AP+gvaeTAAABKUlEQVRIie2UPU7DQBCFP0c0SBQUKSLRpKKmoqJLQ8MhOAQSZ+AQHIKGhoYuoktFBUUkfgIFkuPfeLzrBImnjWa0M2/em9mdBf5qAWyBFugDHaAJbIB1wZ4FsAJegeGEPAGPwLwo+Ry4B74nwMfyBdwB1Rzw2oTgY3kGqmOJp8BzAfhYnoD5X+AV4K4EeJIboDIJfmgBfCwHE/4KcFsyPMkNUE6VLEvwT3KZKlnmHO4C+JiSJXANfBSAJ7lKlSzNgLvAW0H4G3CeKlnqDLgLvBeAvwGLVMlSZsBd4LkA/AlYpkqWUgbcBR5KgN8Dq1TJUmLgLnBXAL4FNqmSpRwDd4HrAvCkZKlHwF3gsgT4Jv0/jGQG7Ga0aT8jZgfsZrRpPyNmB+z+Hb8A7Pgr6UDSCzQAAAAASUVORK5CYII=",
            
            # Ícone de editor
            "editor_24": "iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAYAAADgdz34AAAABmJLR0QA/wD/AP+gvaeTAAAA+ElEQVRIie2UMU4DMRBF3yJRQJMiXS6wR9gjcAZuwBFyBG7AEbgBR+AGkdIgpaCBIoXEJrve9XrGCxIfaTTj8fj/fI8d+K9VwAZ4Bd6BZ+AeWHrBK+AJ+ASmkXwAD8DCC74HvoAvYBfJF/AO3HnAD8AYuALOgVMn/AE4A26BCXDiBK+BM+DGNjhzglfABXANjIAjJ/gFuAQuLYNjJ/gncGUZHAFDJ/gHcG0ZDICBEzwHbiyDPtBzgufArWXQA7pO8Hfgzm6g4wTPgXvLoA20nOA58GAZtICmEzwHHi2DBtBwgufAk2VQB2pO8Bx4tgxqQNUJnv9l+AZNpzPZZFAWJwAAAABJRU5ErkJggg==",
            
            # Ícone de gerador
            "generator_24": "iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAYAAADgdz34AAAABmJLR0QA/wD/AP+gvaeTAAABDElEQVRIie2UMU7DQBBF3wYJCUGBhIREg0SXki5dulyAI+QI3IAjcANuwBG4ARUlXSpKJCSQEAUSEkjg2OuZtbMbKHhSNOP1eP6fHe8C/7UWwBZ4BfrAI7ABVjnBl8AL8AWMgSFwD9znBF8AO+ATuAOqwC1wkwt8BRyAd+AaqAGXuJJdZIJXccAHYA9UgAZQzwRvAXXgGngDPoCzFPAm0ATOgVfgCBxTwdtAC6gCL8AxJbwDdHElOwDHVPAu0LOS7VPCe0AfOFjJUsFtJdvZTlLBByaT2UpSwQHGJpNDangJmJlMUsKLwNRkkgo+MZmkgk9NJqng9nkr5IAPTSap4COTSSr4r/ED/kY9i7GPZPAAAAAASUVORK5CYII=",
            
            # Ícone de logs
            "logs_24": "iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAYAAADgdz34AAAABmJLR0QA/wD/AP+gvaeTAAAA5ElEQVRIie3UMUpDQRCA4S/RQkiRIoWkSGlhYWHhCTyCR/AIHsEjeASP4BEsLCwsLFKkCClCihQiYjGbZH18L89H8GWKZXdm/mF3dhn4b0zgAjd4wDMe8YZn3OMWlxjnBJ/iFk+9sV9c4Sw1fIxrvPfGPnCVGj7CJV57Y++4SQ0fYtEbW+AhNXyARW9sgfvU8D4WvbEFZqnh/ZK8YZYa3scyNbyHZWp4F6vU8C5WqeEdrFPD21inhrdRpIYXKFLDCxSp4QWK1PACRWp4gSI1vECRGl6gSA0vUKSG/xk+AZVfHyPkYKXwAAAAAElFTkSuQmCC",
            
            # Ícone de configurações
            "settings_24": "iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAYAAADgdz34AAAABmJLR0QA/wD/AP+gvaeTAAABP0lEQVRIie2UPU7DQBCFP0c0/DSIhgNwAY7AEbgBR+AGHIEbcASOwAWgQTQUSBGCIAUJx7veXa93bSoepZnx7HvfvNkZ+K9VAefALfAMvAHvwAtwD5wBpSd8AtwAH8AvsI3kB/gEroGxF/wS+AS+gWYgTeBL4MILfgV8AStg3pMX4A5YAh9W+CnwCKyBaU9mgBuwwqsR8ABsgHFPjoDlLnhpgN8C254sgbNd8MIAvwE2PVkAh7vghQF+Dax7MgcOdsELA/wKWPVkBux7wUsD/BJY9mQK7HnBSwP8Alj0ZALsecFLA/wcmPdkDOx6wUsD/AyY9WQE7HjBSwP8FJj2pCK+Yk94aYCfAJOeVMR37AkvDfBjYNSTEfGKveCFAX4EDD0pDXC3lAb40JOhJ6UB7pbSAB96Uhrg/zV+AEejLHSjkF5OAAAAAElFTkSuQmCC"
        }
        
        # Carregar ícones embutidos
        for name, data in embedded_icons.items():
            try:
                icon_data = base64.b64decode(data)
                icon = PhotoImage(data=icon_data)
                self.icons[name] = icon
            except Exception:
                pass
