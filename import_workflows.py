#!/usr/bin/env python3
import json
import os
import requests
import sys
from pathlib import Path

API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyODIxNWJhZS1kNjM3LTRjNzUtYjY3Zi1jMzYyMzY1Y2FiYTYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzY1MzA5NzM1fQ.rGLLjfPWhL_VG_Cndf_xfbeB7Q5tCfjpartKptCiYvU"
BASE_URL = "https://n8n.rootnode.cv/api/v1"
WORKFLOWS_DIR = "/home/user/n8n-install/n8n/backup/workflows"

def clean_workflow(workflow_data):
    """Очищает workflow от полей, которые нельзя импортировать"""
    # Разрешенные поля для API
    allowed_fields = {'name', 'nodes', 'connections', 'settings', 'tags', 'pinData'}
    
    # Создаем новый словарь только с разрешенными полями
    cleaned = {}
    
    # Копируем разрешенные поля
    for field in allowed_fields:
        if field in workflow_data:
            cleaned[field] = workflow_data[field]
    
    # Убеждаемся, что обязательные поля присутствуют
    if 'name' not in cleaned:
        cleaned['name'] = 'Imported Workflow'
    
    if 'nodes' not in cleaned:
        cleaned['nodes'] = []
    
    if 'connections' not in cleaned:
        cleaned['connections'] = {}
    else:
        # Очищаем connections - оставляем только структуру с main и другими стандартными типами
        cleaned_connections = {}
        for node_name, conn_data in cleaned['connections'].items():
            if isinstance(conn_data, dict):
                cleaned_connections[node_name] = conn_data
        cleaned['connections'] = cleaned_connections
    
    if 'settings' not in cleaned:
        cleaned['settings'] = {}
    else:
        # Убеждаемся, что settings - это словарь
        if not isinstance(cleaned['settings'], dict):
            cleaned['settings'] = {}
    
    # Очищаем nodes от credential IDs и других проблемных полей
    allowed_node_fields = {'name', 'type', 'typeVersion', 'position', 'parameters', 'credentials', 'alwaysOutputData', 'onError', 'notes', 'notesInFlow'}
    
    if 'nodes' in cleaned:
        new_nodes = []
        for node in cleaned['nodes']:
            # Создаем новый узел только с разрешенными полями
            new_node = {}
            for field in allowed_node_fields:
                if field in node:
                    new_node[field] = node[field]
            
            # Специальная обработка credentials
            if 'credentials' in new_node:
                cleaned_creds = {}
                for cred_type, cred_data in new_node['credentials'].items():
                    if isinstance(cred_data, dict):
                        # Оставляем только name
                        if 'name' in cred_data:
                            cleaned_creds[cred_type] = {'name': cred_data['name']}
                    else:
                        cleaned_creds[cred_type] = cred_data
                new_node['credentials'] = cleaned_creds
            
            new_nodes.append(new_node)
        cleaned['nodes'] = new_nodes
    
    return cleaned

def import_workflow(file_path):
    """Импортирует один workflow через API"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            workflow_data = json.load(f)
        
        # Очищаем workflow
        workflow_data = clean_workflow(workflow_data)
        
        # Отправляем запрос
        headers = {
            "X-N8N-API-KEY": API_KEY,
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            f"{BASE_URL}/workflows",
            headers=headers,
            json=workflow_data,
            timeout=30
        )
        
        if response.status_code == 200 or response.status_code == 201:
            result = response.json()
            print(f"✓ Успешно импортирован: {workflow_data.get('name', 'Unknown')}")
            return True
        else:
            print(f"✗ Ошибка при импорте {os.path.basename(file_path)}: {response.status_code}")
            print(f"  Ответ: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"✗ Ошибка при обработке {os.path.basename(file_path)}: {str(e)}")
        return False

def main():
    workflows_dir = Path(WORKFLOWS_DIR)
    if not workflows_dir.exists():
        print(f"Каталог {WORKFLOWS_DIR} не найден!")
        sys.exit(1)
    
    workflow_files = list(workflows_dir.glob("*.json"))
    total = len(workflow_files)
    print(f"Найдено {total} workflow файлов для импорта\n")
    
    success_count = 0
    fail_count = 0
    
    for i, workflow_file in enumerate(workflow_files, 1):
        print(f"[{i}/{total}] Импорт {workflow_file.name}...")
        if import_workflow(workflow_file):
            success_count += 1
        else:
            fail_count += 1
        print()
    
    print(f"\nИмпорт завершен:")
    print(f"  Успешно: {success_count}")
    print(f"  Ошибок: {fail_count}")

if __name__ == "__main__":
    main()

