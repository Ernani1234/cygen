"""
Módulo para integração com API de IA.
Implementa comunicação com OpenAI e gerenciamento de custos.
"""

import requests
import json
import os
import time
import threading
import queue
import re
import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

class AIIntegration:
    """
    Módulo para integração com API de IA.
    """
    
    def __init__(self, app):
        """
        Inicializa o módulo de integração com IA.
        
        Args:
            app: Referência à aplicação principal
        """
        self.app = app
        self.config = app.config
        
        # Configurações padrão
        self.default_model = "gpt-3.5-turbo"
        self.default_temperature = 0.7
        self.default_max_tokens = 2000
        
        # Estatísticas de uso
        self.usage_stats = {
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_requests": 0,
            "last_request": None
        }
        
        # Carregar estatísticas salvas
        self.load_usage_stats()
        
        # Fila para comunicação thread-safe
        self.ai_queue = queue.Queue()
    
    def get_api_key(self):
        """
        Obtém a chave da API das configurações.
        
        Returns:
            str: Chave da API ou None se não estiver configurada
        """
        return self.config.get("api_key")
    
    def set_api_key(self, api_key):
        """
        Define a chave da API nas configurações.
        
        Args:
            api_key: Chave da API
        """
        self.config.set("api_key", api_key)
        self.config.save()
    
    def get_model(self):
        """
        Obtém o modelo configurado.
        
        Returns:
            str: Nome do modelo
        """
        return self.config.get("model", self.default_model)
    
    def set_model(self, model):
        """
        Define o modelo nas configurações.
        
        Args:
            model: Nome do modelo
        """
        self.config.set("model", model)
        self.config.save()
    
    def get_temperature(self):
        """
        Obtém a temperatura configurada.
        
        Returns:
            float: Valor da temperatura
        """
        return float(self.config.get("temperature", self.default_temperature))
    
    def set_temperature(self, temperature):
        """
        Define a temperatura nas configurações.
        
        Args:
            temperature: Valor da temperatura
        """
        self.config.set("temperature", float(temperature))
        self.config.save()
    
    def get_max_tokens(self):
        """
        Obtém o limite de tokens configurado.
        
        Returns:
            int: Limite de tokens
        """
        return int(self.config.get("max_tokens", self.default_max_tokens))
    
    def set_max_tokens(self, max_tokens):
        """
        Define o limite de tokens nas configurações.
        
        Args:
            max_tokens: Limite de tokens
        """
        self.config.set("max_tokens", int(max_tokens))
        self.config.save()
    
    def get_usage_stats(self):
        """
        Obtém estatísticas de uso da API.
        
        Returns:
            dict: Estatísticas de uso
        """
        return self.usage_stats
    
    def load_usage_stats(self):
        """Carrega estatísticas de uso salvas"""
        stats_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "usage_stats.json")
        
        try:
            if os.path.exists(stats_file):
                with open(stats_file, 'r') as f:
                    self.usage_stats = json.load(f)
        except Exception as e:
            print(f"Erro ao carregar estatísticas de uso: {str(e)}")
    
    def save_usage_stats(self):
        """Salva estatísticas de uso"""
        stats_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        os.makedirs(stats_dir, exist_ok=True)
        
        stats_file = os.path.join(stats_dir, "usage_stats.json")
        
        try:
            with open(stats_file, 'w') as f:
                json.dump(self.usage_stats, f)
        except Exception as e:
            print(f"Erro ao salvar estatísticas de uso: {str(e)}")
    
    def update_usage_stats(self, response_data):
        """
        Atualiza estatísticas de uso com base na resposta da API.
        
        Args:
            response_data: Dados da resposta da API
        """
        if "usage" in response_data:
            usage = response_data["usage"]
            
            self.usage_stats["prompt_tokens"] += usage.get("prompt_tokens", 0)
            self.usage_stats["completion_tokens"] += usage.get("completion_tokens", 0)
            self.usage_stats["total_tokens"] += usage.get("total_tokens", 0)
            self.usage_stats["total_requests"] += 1
            self.usage_stats["last_request"] = time.time()
            
            # Salvar estatísticas
            self.save_usage_stats()
    
    def estimate_tokens(self, messages):
        """
        Estima o número de tokens em uma lista de mensagens.
        
        Args:
            messages: Lista de mensagens
        
        Returns:
            int: Estimativa de tokens
        """
        # Estimativa simples: aproximadamente 4 caracteres por token
        total_chars = 0
        
        for message in messages:
            total_chars += len(message.get("content", ""))
        
        return total_chars // 4
    
    def estimate_cost(self, tokens):
        """
        Estima o custo em dólares com base no número de tokens.
        
        Args:
            tokens: Número de tokens
        
        Returns:
            float: Custo estimado em dólares
        """
        # Custo aproximado para gpt-3.5-turbo: $0.0015 por 1K tokens
        return (tokens / 1000) * 0.0015
    
    def confirm_api_cost(self, tokens):
        """
        Solicita confirmação do usuário para o custo estimado.
        
        Args:
            tokens: Número de tokens
        
        Returns:
            bool: True se confirmado, False caso contrário
        """
        cost = self.estimate_cost(tokens)
        
        # Referência de custo: "1,385 requests(6,024,231 tokens) = $6.94(dollar)"
        message = f"Estimativa de uso:\n\n" \
                 f"Tokens: {tokens:,}\n" \
                 f"Custo: ${cost:.4f} USD\n\n" \
                 f"Referência: 1,385 requests(6,024,231 tokens) = $6.94(dollar)\n\n" \
                 f"Deseja prosseguir?"
        
        return messagebox.askyesno("Confirmar Custo da API", message)
    
    def chat_completion(self, messages, context=None, system_prompt=None):
        """
        Realiza uma requisição de chat completion.
        
        Args:
            messages: Lista de mensagens
            context: Contexto adicional (opcional)
            system_prompt: Prompt de sistema personalizado (opcional)
        
        Returns:
            dict: Resultado da requisição
        """
        api_key = self.get_api_key()
        if not api_key:
            return {
                "success": False,
                "error": "Chave da API não configurada. Configure nas Configurações."
            }
        
        # Preparar mensagens
        api_messages = []
        
        # Adicionar prompt de sistema
        if system_prompt:
            api_messages.append({
                "role": "system",
                "content": system_prompt
            })
        else:
            api_messages.append({
                "role": "system",
                "content": "Você é um assistente especializado em testes automatizados Cypress. Ajude o usuário a criar, melhorar e depurar testes Cypress."
            })
        
        # Adicionar contexto se fornecido
        if context:
            api_messages.append({
                "role": "system",
                "content": context
            })
        
        # Adicionar mensagens do usuário
        for message in messages:
            api_messages.append(message)
        
        # Estimar tokens
        estimated_tokens = self.estimate_tokens(api_messages) + self.get_max_tokens()
        
        # Confirmar custo
        if not self.confirm_api_cost(estimated_tokens):
            return {
                "success": False,
                "error": "Operação cancelada pelo usuário."
            }
        
        # Preparar requisição
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        data = {
            "model": self.get_model(),
            "messages": api_messages,
            "temperature": self.get_temperature(),
            "max_tokens": self.get_max_tokens()
        }
        
        try:
            # Fazer requisição
            response = requests.post(url, headers=headers, json=data)
            response_data = response.json()
            
            if response.status_code == 200:
                # Extrair resposta
                content = response_data["choices"][0]["message"]["content"]
                
                # Atualizar estatísticas
                self.update_usage_stats(response_data)
                
                return {
                    "success": True,
                    "response": content
                }
            else:
                error = response_data.get("error", {}).get("message", "Erro desconhecido")
                return {
                    "success": False,
                    "error": error
                }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def generate_test(self, actions, options):
        """
        Gera um teste Cypress com base nas ações capturadas.
        
        Args:
            actions: Lista de ações capturadas
            options: Opções de geração
        
        Returns:
            dict: Resultado da geração
        """
        # Preparar prompt
        system_prompt = """Você é um especialista em automação de testes Cypress. 
Sua tarefa é gerar um teste Cypress completo e funcional com base nas ações do usuário capturadas.
Siga estas diretrizes:
1. Use a estrutura padrão de testes Cypress com describe e it
2. Implemente verificações (assertions) relevantes
3. Use seletores estáveis e confiáveis
4. Adicione comentários explicativos
5. Implemente boas práticas de teste
6. Organize o código de forma clara e legível
7. Inclua tratamento de esperas e timeouts quando necessário"""
        
        # Preparar contexto
        context = f"""
Informações do teste a ser gerado:
- Nome: {options.get('name', 'Teste Automatizado')}
- Descrição: {options.get('description', 'Teste gerado automaticamente')}
- URL base: {options.get('baseUrl', '')}

Ações capturadas:
```
{json.dumps(actions, indent=2)}
```

Gere um teste Cypress completo e funcional com base nessas ações.
"""
        
        # Fazer requisição
        return self.chat_completion([], context, system_prompt)
    
    def improve_test(self, test_code, instructions):
        """
        Melhora um teste Cypress existente.
        
        Args:
            test_code: Código do teste
            instructions: Instruções para melhoria
        
        Returns:
            dict: Resultado da melhoria
        """
        # Preparar prompt
        system_prompt = """Você é um especialista em automação de testes Cypress.
Sua tarefa é melhorar o teste Cypress fornecido de acordo com as instruções do usuário.
Siga estas diretrizes:
1. Mantenha a estrutura básica do teste
2. Implemente as melhorias solicitadas
3. Adicione comentários explicando as mudanças
4. Siga boas práticas de teste
5. Mantenha o código limpo e legível"""
        
        # Preparar contexto
        context = f"""
Código do teste atual:
```javascript
{test_code}
```

Instruções para melhoria:
{instructions}

Forneça o código melhorado do teste Cypress.
"""
        
        # Fazer requisição
        return self.chat_completion([], context, system_prompt)
    
    def debug_test(self, test_code, error_message):
        """
        Depura um teste Cypress com erro.
        
        Args:
            test_code: Código do teste
            error_message: Mensagem de erro
        
        Returns:
            dict: Resultado da depuração
        """
        # Preparar prompt
        system_prompt = """Você é um especialista em automação de testes Cypress.
Sua tarefa é depurar o teste Cypress fornecido com base na mensagem de erro.
Siga estas diretrizes:
1. Identifique a causa raiz do erro
2. Proponha uma solução clara
3. Forneça o código corrigido
4. Explique as mudanças feitas
5. Sugira melhorias adicionais se apropriado"""
        
        # Preparar contexto
        context = f"""
Código do teste com erro:
```javascript
{test_code}
```

Mensagem de erro:
```
{error_message}
```

Forneça o código corrigido e uma explicação do problema.
"""
        
        # Fazer requisição
        return self.chat_completion([], context, system_prompt)
