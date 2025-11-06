#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pdfplumber
import json
import re
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

def clean_text(text: str) -> str:
    """Remove caracteres estranhos e normaliza texto"""
    if not text:
        return ""
    # Remover caracteres de controle
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
    # Normalizar espaços
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_header_info(text: str) -> Dict[str, Any]:
    """Extrai informações do cabeçalho do documento"""
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
    
    lines = text.split('\n')
    
    # Extrair nome da empresa
    for line in lines[:5]:
        if "Empresa:" in line:
            match = re.search(r'Empresa:\s*(.+?)(?:\s+Folha:|$)', line)
            if match:
                header["company"] = clean_text(match.group(1))
            break
    
    # Extrair CNPJ
    cnpj_match = re.search(r'C\.N\.P\.J\.:\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})', text)
    if cnpj_match:
        header["cnpj"] = cnpj_match.group(1)
    
    # Extrair número do livro
    book_match = re.search(r'Número livro:\s*(\d+)', text)
    if book_match:
        header["book_number"] = book_match.group(1)
    
    # Extrair período
    period_match = re.search(r'Período:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})', text)
    if period_match:
        header["period"] = f"{period_match.group(1)} - {period_match.group(2)}"
    
    # Extrair data de emissão
    date_match = re.search(r'Emissão:\s*(\d{2}/\d{2}/\d{4})', text)
    if date_match:
        header["issue_date"] = date_match.group(1)
    
    # Extrair hora
    time_match = re.search(r'Hora:\s*(\d{2}:\d{2}:\d{2})', text)
    if time_match:
        header["time"] = time_match.group(1)
    
    # Extrair tipo de relatório
    if "BALANCETE" in text.upper():
        header["report_type"] = "BALANCETE CONSOLIDADO" if "CONSOLIDADO" in text.upper() else "BALANCETE"
    
    # Extrair número da página (Folha)
    page_match = re.search(r'Folha:\s*(\d+)', text)
    if page_match:
        header["page"] = page_match.group(1)
    
    return header

def clean_account_name(name: str) -> str:
    """Limpa nome da conta removendo caracteres numéricos misturados"""
    if not name:
        return ""
    
    # Remover padrões como "CIRCU2L1A.N1TE" -> "CIRCULANTE"
    # Estratégia: remover dígitos isolados entre letras, mas manter números que fazem parte de códigos
    
    # Primeiro, tentar identificar e remover códigos no início
    name = re.sub(r'^\d+\s+', '', name)  # Remove código no início
    
    # Remover dígitos isolados que estão misturados com letras (mas não números completos)
    # Padrão: letra + dígito + letra -> manter apenas letras
    name = re.sub(r'([A-Za-z])(\d+)([A-Za-z])', r'\1\3', name)
    
    # Remover dígitos isolados no meio de palavras
    name = re.sub(r'([A-Za-z])(\d)([A-Za-z])', r'\1\3', name)
    
    # Limpar múltiplos espaços
    name = re.sub(r'\s+', ' ', name)
    
    return name.strip()

def parse_monetary_value(value: str) -> Optional[str]:
    """Parse e limpa valor monetário"""
    if not value:
        return None
    
    # Remover caracteres não numéricos exceto vírgula e ponto
    cleaned = re.sub(r'[^\d.,]', '', value)
    
    # Validar formato (deve ter vírgula e 2 decimais)
    if re.match(r'^[\d\.]+,\d{2}$', cleaned):
        return cleaned
    
    return None

def parse_data_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse uma linha de dados do balancete"""
    if not line or len(line.strip()) < 5:
        return None
    
    line = clean_text(line)
    
    # Pular linhas de cabeçalho ou rodapé
    skip_keywords = [
        'EMPRESA:', 'C.N.P.J.:', 'PERÍODO:', 'EMISSÃO:', 'HORA:', 
        'BALANCETE', 'CÓDIGO', 'CLASSIFICAÇÃO', 'DESCRIÇÃO', 
        'SALDO ANTERIOR', 'DÉBITO', 'CRÉDITO', 'SALDO ATUAL',
        'CONSOLIDADO', 'CPF:', '_______________________________________',
        'GILMIER', 'CRISTIANI', 'MIRI', 'ZUCOLOTO'
    ]
    
    if any(keyword in line.upper() for keyword in skip_keywords):
        return None
    
    # Encontrar valores monetários
    monetary_pattern = r'[\d\.]+,\d{2}'
    monetary_matches = list(re.finditer(monetary_pattern, line))
    
    if not monetary_matches:
        # Linha sem valores monetários - pode ser categoria
        if len(line) > 15:
            return {
                "code": None,
                "classification": None,
                "account": clean_account_name(line),
                "previous_balance": None,
                "current_balance": None,
                "debit": None,
                "credit": None,
                "parent_category": None
            }
        return None
    
    # Extrair valores monetários
    monetary_values = [m.group() for m in monetary_matches]
    
    # Determinar índices dos valores na linha
    value_positions = [(m.start(), m.end(), m.group()) for m in monetary_matches]
    
    # Dividir linha em partes antes e depois dos valores
    parts_before_values = line[:value_positions[0][0]].strip()
    parts_after_values = line[value_positions[-1][1]:].strip() if value_positions else ""
    
    # Parse código e classificação da parte antes dos valores
    code = None
    classification = None
    account_start_idx = 0
    
    # Procurar classificação (formato X.X.XX.XXX.XX)
    classification_match = re.search(r'(\d+\.\d+\.\d+\.\d+\.\d+)', parts_before_values)
    if classification_match:
        classification = classification_match.group(1)
        account_start_idx = classification_match.end()
    
    # Procurar código (4-6 dígitos, não classificação)
    if not classification:
        code_match = re.search(r'\b(\d{4,6})\b', parts_before_values)
        if code_match:
            code = code_match.group(1)
            account_start_idx = code_match.end()
    
    # Se encontrou código antes da classificação
    if classification:
        code_before = parts_before_values[:classification_match.start()].strip()
        code_match = re.search(r'\b(\d{4,6})\b', code_before)
        if code_match:
            code = code_match.group(1)
    
    # Extrair nome da conta
    account_text = parts_before_values[account_start_idx:].strip()
    
    # Se não encontrou texto da conta antes dos valores, tentar depois
    if not account_text and parts_after_values:
        account_text = parts_after_values
    
    # Limpar nome da conta
    account = clean_account_name(account_text)
    
    if not account:
        return None
    
    # Determinar valores monetários
    previous_balance = None
    current_balance = None
    debit = None
    credit = None
    
    if len(monetary_values) >= 4:
        previous_balance = parse_monetary_value(monetary_values[0])
        debit = parse_monetary_value(monetary_values[1])
        credit = parse_monetary_value(monetary_values[2])
        current_balance = parse_monetary_value(monetary_values[3])
    elif len(monetary_values) == 3:
        previous_balance = parse_monetary_value(monetary_values[0])
        debit = parse_monetary_value(monetary_values[1])
        credit = parse_monetary_value(monetary_values[2])
    elif len(monetary_values) == 2:
        previous_balance = parse_monetary_value(monetary_values[0])
        current_balance = parse_monetary_value(monetary_values[1])
    elif len(monetary_values) == 1:
        current_balance = parse_monetary_value(monetary_values[0])
    
    return {
        "code": code if code else None,
        "classification": classification if classification else None,
        "account": account,
        "previous_balance": previous_balance if previous_balance else None,
        "current_balance": current_balance if current_balance else None,
        "debit": debit if debit else None,
        "credit": credit if credit else None,
        "parent_category": None
    }

def extract_bold_categories(chars: List[Dict]) -> Dict[int, str]:
    """Extrai categorias em negrito agrupadas por linha"""
    bold_by_line = defaultdict(str)
    
    current_bold = ""
    current_y = None
    
    for char in chars:
        is_bold = char.get('fontname', '').upper().find('BOLD') != -1 or char.get('bold', False)
        char_y = char.get('top', 0)
        char_text = char.get('text', '')
        
        if is_bold and char_text:
            # Agrupar caracteres na mesma linha (tolerância de 3 pixels)
            if current_y is None or abs(char_y - current_y) < 3:
                current_bold += char_text
                current_y = char_y
            else:
                # Nova linha
                if current_bold.strip() and len(current_bold.strip()) > 5:
                    y_key = int(current_y) if current_y else 0
                    existing = bold_by_line[y_key]
                    if len(current_bold.strip()) > len(existing):
                        bold_by_line[y_key] = clean_text(current_bold)
                current_bold = char_text
                current_y = char_y
        else:
            if current_bold.strip():
                y_key = int(current_y) if current_y else 0
                existing = bold_by_line[y_key]
                if len(current_bold.strip()) > len(existing):
                    bold_by_line[y_key] = clean_text(current_bold)
                current_bold = ""
                current_y = None
    
    if current_bold.strip():
        y_key = int(current_y) if current_y else 0
        existing = bold_by_line[y_key]
        if len(current_bold.strip()) > len(existing):
            bold_by_line[y_key] = clean_text(current_bold)
    
    return dict(bold_by_line)

def extract_data_from_pdf(pdf_path: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Extrai dados do PDF"""
    header = {}
    all_data = []
    parent_categories = []  # Stack de categorias pai
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            # Extrair texto
            text = page.extract_text()
            if not text:
                continue
            
            # Extrair cabeçalho apenas da primeira página
            if page_num == 1:
                header = extract_header_info(text)
            
            # Extrair categorias em negrito
            chars = page.chars
            bold_categories = extract_bold_categories(chars)
            
            # Processar linhas
            lines = text.split('\n')
            
            for line_idx, line in enumerate(lines):
                line = line.strip()
                if not line or len(line) < 5:
                    continue
                
                # Pular linhas de cabeçalho
                skip_keywords = [
                    'EMPRESA:', 'C.N.P.J.:', 'PERÍODO:', 'EMISSÃO:', 'HORA:', 
                    'BALANCETE', 'CÓDIGO', 'CLASSIFICAÇÃO', 'DESCRIÇÃO', 
                    'SALDO ANTERIOR', 'DÉBITO', 'CRÉDITO', 'SALDO ATUAL',
                    'CONSOLIDADO', 'CPF:', '_______________________________________'
                ]
                
                if any(keyword in line.upper() for keyword in skip_keywords):
                    continue
                
                # Verificar se a linha contém uma categoria em negrito
                line_y = None
                for char in chars:
                    if char.get('text', '') and line and char.get('text', '')[0] == line[0]:
                        line_y = char.get('top', 0)
                        break
                
                is_category = False
                if line_y is not None:
                    y_normalized = int(line_y)
                    # Verificar se há categoria em negrito próxima a esta linha
                    for bold_y, bold_text in bold_categories.items():
                        if abs(y_normalized - bold_y) < 5:
                            # Verificar se o texto em negrito está na linha
                            if bold_text.upper() in line.upper() or \
                               (len(bold_text) > 10 and bold_text[:15].upper() in line.upper()):
                                # É uma categoria principal
                                cleaned_bold = clean_account_name(bold_text)
                                if cleaned_bold and len(cleaned_bold) > 5:
                                    # Atualizar stack de categorias
                                    # Remover categorias mais específicas se esta for mais geral
                                    parent_categories = [c for c in parent_categories if not cleaned_bold.upper().startswith(c.upper())]
                                    parent_categories.append(cleaned_bold)
                                    is_category = True
                                    
                                    # Criar entrada para a categoria
                                    entry = parse_data_line(line)
                                    if entry:
                                        entry['parent_category'] = None
                                        all_data.append(entry)
                                    break
                
                if not is_category:
                    # Parse linha normal
                    entry = parse_data_line(line)
                    if entry:
                        # Associar categoria pai mais recente
                        if parent_categories:
                            entry['parent_category'] = parent_categories[-1]
                        all_data.append(entry)
    
    return header, all_data

def main():
    pdf_path = "/workspace/balancete.pdf"
    
    print("Extraindo dados do PDF...")
    header, data = extract_data_from_pdf(pdf_path)
    
    result = {
        "header": header,
        "data": data
    }
    
    # Salvar JSON
    output_path = "/workspace/balancete.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=4)
    
    print(f"Extracção concluída! {len(data)} entradas encontradas.")
    print(f"JSON salvo em: {output_path}")
    
    # Imprimir JSON completo
    print("\n" + "="*80)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
