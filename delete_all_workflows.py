#!/usr/bin/env python3
import requests
import sys

API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyODIxNWJhZS1kNjM3LTRjNzUtYjY3Zi1jMzYyMzY1Y2FiYTYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzY1MzA5NzM1fQ.rGLLjfPWhL_VG_Cndf_xfbeB7Q5tCfjpartKptCiYvU"
BASE_URL = "https://n8n.rootnode.cv/api/v1"

def get_all_workflows():
    """Получает список всех workflows"""
    headers = {"X-N8N-API-KEY": API_KEY}
    response = requests.get(f"{BASE_URL}/workflows", headers=headers, timeout=30)
    
    if response.status_code == 200:
        data = response.json()
        return data.get('data', [])
    else:
        print(f"Ошибка при получении списка workflows: {response.status_code}")
        print(response.text)
        return []

def delete_workflow(workflow_id):
    """Удаляет один workflow"""
    headers = {"X-N8N-API-KEY": API_KEY}
    response = requests.delete(f"{BASE_URL}/workflows/{workflow_id}", headers=headers, timeout=30)
    
    if response.status_code == 200:
        return True
    else:
        print(f"  Ошибка: {response.status_code} - {response.text[:100]}")
        return False

def main():
    print("Получение списка всех workflows...")
    workflows = get_all_workflows()
    
    if not workflows:
        print("Workflows не найдены или ошибка при получении списка.")
        sys.exit(1)
    
    total = len(workflows)
    print(f"Найдено {total} workflows для удаления\n")
    
    # Подтверждение
    confirm = input(f"Вы уверены, что хотите удалить все {total} workflows? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Операция отменена.")
        sys.exit(0)
    
    print("\nНачинаю удаление...\n")
    
    success_count = 0
    fail_count = 0
    
    for i, workflow in enumerate(workflows, 1):
        workflow_id = workflow.get('id')
        workflow_name = workflow.get('name', 'Unknown')
        
        print(f"[{i}/{total}] Удаление: {workflow_name}...", end=' ')
        
        if delete_workflow(workflow_id):
            print("✓")
            success_count += 1
        else:
            print("✗")
            fail_count += 1
    
    print(f"\nУдаление завершено:")
    print(f"  Успешно удалено: {success_count}")
    print(f"  Ошибок: {fail_count}")

if __name__ == "__main__":
    main()

