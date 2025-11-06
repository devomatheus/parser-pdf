#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parser Final de Balancete Financeiro
Extrai dados de PDF e gera JSON estruturado conforme especificação.
"""

import pdfplumber
import json
import re

def parse_balancete_pdf(pdf_path):
    """
    Realiza parse completo do PDF do balancete.
    """
    result = {
        "header": {},
        "data": []
    }
    
    with pdfplumber.open(pdf_path) as pdf:
        all_text = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_text += text + "\n"
        
        result["header"] = extract_header(all_text)
        result["data"] = extract_data(all_text)
    
    return result

def extract_header(text):
    """
    Extrai informações do cabeçalho.
    """
    header = {
        "company": None,
        "cnpj": None,
        "report_type": None,
        "period": None,
        "issue_date": None,
        "time": None,
        "page": None,
        "book_number": None
    }
    
    lines = text.split('\n')[:25]
    
    for line in lines:
        # Empresa
        if "Empresa:" in line:
            match = re.search(r'Empresa:\s*([A-ZÀ-Ú\s]+?)(?:\s+Folha:|$)', line)
            if match:
                header["company"] = match.group(1).strip()
        
        # CNPJ
        if re.search(r'C\.N\.P\.J\.|CNPJ', line):
            match = re.search(r'(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})', line)
            if match:
                header["cnpj"] = match.group(1)
        
        # Número do livro
        if "livro:" in line.lower():
            match = re.search(r'livro:\s*(\d+)', line, re.IGNORECASE)
            if match:
                header["book_number"] = match.group(1)
        
        # Período
        if "Período:" in line:
            match = re.search(r'(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})', line)
            if match:
                header["period"] = f"{match.group(1)} - {match.group(2)}"
        
        # Data de emissão
        if "Emissão:" in line:
            match = re.search(r'Emissão:\s*(\d{2}/\d{2}/\d{4})', line)
            if match:
                header["issue_date"] = match.group(1)
        
        # Hora
        if "Hora:" in line:
            match = re.search(r'Hora:\s*(\d{2}:\d{2}:\d{2})', line)
            if match:
                header["time"] = match.group(1)
        
        # Tipo de relatório
        if "BALANCETE" in line and not header["report_type"]:
            header["report_type"] = "BALANCETE CONSOLIDADO"
    
    return header

def extract_data(text):
    """
    Extrai todas as entradas de dados do texto.
    """
    entries = []
    lines = text.split('\n')
    current_parent = None
    
    for line in lines:
        # Pular linhas não relevantes
        if skip_line(line):
            continue
        
        entry = parse_entry_line(line)
        
        if entry:
            # Detectar e definir categoria pai
            if is_category(entry):
                current_parent = entry['account']
            else:
                entry['parent_category'] = current_parent
            
            entries.append(entry)
    
    return entries

def skip_line(line):
    """
    Determina se uma linha deve ser ignorada.
    """
    if not line.strip() or len(line.strip()) < 8:
        return True
    
    skip_patterns = [
        'Empresa:', 'C.N.P.J.', 'Período:', 'Emissão:', 'Hora:', 'Folha:',
        'CONSOLIDADO', 'livro:', 'Código Classificação',
        'RESUMO DO BALANCETE', 'CONTAS DEVEDORAS', 'CONTAS CREDORAS',
        'RESULTADO DO MES', 'RESULTADO DO EXERCÍCIO', 'ATIVO.*PASSIVO.*RECEITAS',
        'Reg. no CRC', 'CPF:', '^BALANCETE$', '^_{4,}'
    ]
    
    for pattern in skip_patterns:
        if re.search(pattern, line):
            return True
    
    return False

def parse_entry_line(line):
    """
    Extrai uma entrada de dados de uma linha.
    """
    original_line = line
    line = line.strip()
    
    # Padrão de valores monetários (formato brasileiro)
    value_pattern = r'-?\d{1,3}(?:\.\d{3})*,\d{2}'
    values = re.findall(value_pattern, line)
    
    # Linha deve ter pelo menos um valor
    if not values:
        return None
    
    # Extrair código (1-6 dígitos no início)
    code = None
    code_match = re.match(r'^(\d{1,6})(?:\s|[A-ZÀ-Ú])', line)
    if code_match:
        code = code_match.group(1)
    
    # Extrair classificação (X.X.XX.XXX...)
    # Classificações típicas: 1.1.01, 1.1.01.020.001, etc.
    # NÃO devem ser valores grandes como 473.793.521
    classification = None
    class_pattern = r'\b(\d{1,2}\.\d{1,2}(?:\.\d{1,3}){1,})\b'
    class_matches = re.findall(class_pattern, line)
    if class_matches:
        # Filtrar classificações válidas (não muito longas, não valores)
        valid_classifications = [c for c in class_matches if len(c) <= 20 and c.count('.') >= 2]
        if valid_classifications:
            # Pegar a classificação mais detalhada
            classification = max(valid_classifications, key=lambda x: x.count('.'))
    
    # Extrair descrição da conta
    account = extract_account_description(line, code, classification, values)
    
    if not account or len(account) < 2:
        return None
    
    # Limpar descrição
    account = clean_description(account)
    
    # Criar entrada
    entry = {
        "code": code,
        "classification": classification,
        "account": account,
        "previous_balance": None,
        "debit": None,
        "credit": None,
        "current_balance": None,
        "parent_category": None
    }
    
    # Atribuir valores (ordem: saldo anterior, débito, crédito, saldo atual)
    if len(values) >= 4:
        entry["previous_balance"] = values[-4]
        entry["debit"] = values[-3]
        entry["credit"] = values[-2]
        entry["current_balance"] = values[-1]
    elif len(values) == 3:
        entry["previous_balance"] = values[0]
        entry["debit"] = values[1]
        entry["current_balance"] = values[2]
    elif len(values) == 2:
        entry["debit"] = values[0]
        entry["current_balance"] = values[1]
    elif len(values) == 1:
        entry["current_balance"] = values[0]
    
    return entry

def extract_account_description(line, code, classification, values):
    """
    Extrai a descrição da conta removendo código, classificação e valores.
    """
    account = line
    
    # Remover código
    if code:
        account = re.sub(r'^\d{1,6}\s*', '', account, count=1)
    
    # Remover classificação
    if classification:
        account = account.replace(classification, ' ')
    
    # Remover todos os valores
    for value in values:
        account = account.replace(value, ' ', 1)
    
    # Limpar números soltos residuais
    account = re.sub(r'\b\d+\.\d+\b', ' ', account)
    account = re.sub(r'\b\d{1,3}\b(?!\d)', ' ', account)
    
    return account

def clean_description(text):
    """
    Limpa e normaliza a descrição da conta.
    Remove artefatos de texto mesclado e padroniza formatação.
    """
    # Remover caracteres especiais problemáticos
    text = re.sub(r'[^\wÀ-ú\s\-,/().]', ' ', text)
    
    # Normalizar espaços múltiplos
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Tentar detectar e corrigir padrões de texto mesclado
    # Ex: "CAIXA4 1.1.01.01 CAIXA" -> "CAIXA"
    # Quando há repetição de palavra, manter apenas uma
    words = text.split()
    if len(words) >= 2:
        # Se primeira e última palavra são similares, pode ser duplicação
        if words[0].upper() == words[-1].upper():
            text = words[-1]
        # Remover palavras de 1-2 letras isoladas no meio
        clean_words = []
        for i, word in enumerate(words):
            if len(word) > 2 or i == 0 or i == len(words) - 1:
                clean_words.append(word)
        if clean_words:
            text = ' '.join(clean_words)
    
    return text.strip()

def is_category(entry):
    """
    Determina se uma entrada é uma categoria pai.
    """
    if not entry or not entry.get('account'):
        return False
    
    account = entry['account']
    classification = entry.get('classification', '')
    
    # Critérios para categoria:
    # 1. Maiúsculas
    # 2. Classificação simples (poucos níveis) ou sem classificação
    # 3. Descrição relativamente curta
    
    is_upper = account.isupper()
    is_short = len(account.split()) <= 6
    simple_class = not classification or classification.count('.') <= 2
    
    return is_upper and is_short and simple_class

def save_json(data, output_path):
    """
    Salva dados em formato JSON.
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def print_report(result, output_path):
    """
    Imprime relatório de processamento.
    """
    print("\n" + "=" * 80)
    print(" " * 22 + "BALANCETE - PARSE FINALIZADO")
    print("=" * 80 + "\n")
    
    print(f"✅ Arquivo gerado: {output_path}")
    print(f"📊 Total de entradas: {len(result['data'])}\n")
    
    # Estatísticas
    with_code = sum(1 for e in result['data'] if e.get('code'))
    with_class = sum(1 for e in result['data'] if e.get('classification') and '.' in str(e['classification']))
    with_parent = sum(1 for e in result['data'] if e.get('parent_category'))
    
    print("📈 Estatísticas:")
    print(f"  • Entradas com código: {with_code} ({with_code/len(result['data'])*100:.1f}%)")
    print(f"  • Entradas com classificação: {with_class} ({with_class/len(result['data'])*100:.1f}%)")
    print(f"  • Entradas com categoria pai: {with_parent} ({with_parent/len(result['data'])*100:.1f}%)")
    
    print("\n" + "=" * 80)
    print("CABEÇALHO DO DOCUMENTO")
    print("=" * 80 + "\n")
    
    for key, value in result['header'].items():
        if value:
            label = key.replace('_', ' ').title()
            print(f"  {label:.<30} {value}")
    
    print("\n" + "=" * 80)
    print("VISUALIZAÇÃO JSON (Primeiras 3 entradas completas)")
    print("=" * 80 + "\n")
    
    sample = {
        "header": result['header'],
        "data": result['data'][:3]
    }
    print(json.dumps(sample, ensure_ascii=False, indent=2))
    
    print("\n" + "=" * 80)
    print("✨ PROCESSAMENTO CONCLUÍDO COM SUCESSO!")
    print("=" * 80 + "\n")

def main():
    """
    Função principal.
    """
    pdf_path = "/workspace/balancete.pdf"
    output_path = "/workspace/balancete.json"
    
    print("\n🔍 Iniciando parse do arquivo PDF...")
    print(f"📄 Origem: {pdf_path}\n")
    
    # Parse do PDF
    result = parse_balancete_pdf(pdf_path)
    
    # Salvar JSON
    save_json(result, output_path)
    
    # Imprimir relatório
    print_report(result, output_path)
    
    return result

if __name__ == "__main__":
    main()
