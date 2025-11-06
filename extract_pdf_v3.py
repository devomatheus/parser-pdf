#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pdfplumber
import json
import re
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

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
                header["company"] = match.group(1).strip()
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

def reconstruct_text_from_chars(chars: List[Dict], separate_bold: bool = False) -> List[Tuple[str, float, bool]]:
    """Reconstrói texto a partir de caracteres, agrupando por linha"""
    # Agrupar caracteres por linha (posição Y)
    lines_dict = defaultdict(list)
    
    for char in chars:
        y = round(char.get('top', 0))
        lines_dict[y].append(char)
    
    # Ordenar linhas por Y (de cima para baixo)
    sorted_lines = sorted(lines_dict.items(), key=lambda x: x[0], reverse=True)
    
    reconstructed_lines = []
    
    for y, line_chars in sorted_lines:
        # Ordenar caracteres na linha por X (da esquerda para direita)
        line_chars.sort(key=lambda c: c.get('x0', 0))
        
        # Reconstruir texto da linha
        line_text = ""
        is_bold_line = False
        
        for char in line_chars:
            char_text = char.get('text', '')
            if char_text:
                line_text += char_text
                # Verificar se algum caractere é negrito
                if char.get('fontname', '').upper().find('BOLD') != -1 or char.get('bold', False):
                    is_bold_line = True
        
        if line_text.strip():
            reconstructed_lines.append((line_text.strip(), y, is_bold_line))
    
    return reconstructed_lines

def clean_account_name(name: str) -> str:
    """Limpa nome da conta"""
    if not name:
        return ""
    
    # Remover códigos numéricos no início (4-6 dígitos isolados)
    name = re.sub(r'^\d{4,6}\s+', '', name)
    
    # Remover padrões como "CAIXA4" -> "CAIXA"
    name = re.sub(r'([A-Za-z])(\d+)(\s|$)', r'\1\3', name)
    
    # Remover dígitos isolados entre letras (mas manter números que são parte de códigos de classificação)
    # Primeiro, proteger códigos de classificação
    protected = []
    for match in re.finditer(r'\d+\.\d+\.\d+\.\d+\.\d+', name):
        protected.append((match.start(), match.end(), match.group()))
    
    # Remover dígitos isolados fora das áreas protegidas
    result = []
    last_end = 0
    
    for start, end, code in protected:
        result.append(name[last_end:start])
        result.append(code)
        last_end = end
    
    result.append(name[last_end:])
    name = ''.join(result)
    
    # Agora remover dígitos isolados
    name = re.sub(r'([A-Za-zÀ-ÿ])(\d)([A-Za-zÀ-ÿ])', r'\1\3', name)
    
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

def parse_data_line(line: str, is_bold: bool = False) -> Optional[Dict[str, Any]]:
    """Parse uma linha de dados do balancete"""
    if not line or len(line.strip()) < 3:
        return None
    
    line = line.strip()
    
    # Pular linhas de cabeçalho ou rodapé
    skip_keywords = [
        'EMPRESA:', 'C.N.P.J.:', 'PERÍODO:', 'EMISSÃO:', 'HORA:', 
        'BALANCETE', 'CÓDIGO', 'CLASSIFICAÇÃO', 'DESCRIÇÃO', 
        'SALDO ANTERIOR', 'DÉBITO', 'CRÉDITO', 'SALDO ATUAL',
        'CONSOLIDADO', 'CPF:', '_______________________________________',
        'GILMIER', 'CRISTIANI', 'MIRI', 'ZUCOLOTO', 'NÚMERO LIVRO'
    ]
    
    if any(keyword in line.upper() for keyword in skip_keywords):
        return None
    
    # Encontrar valores monetários
    monetary_pattern = r'[\d\.]+,\d{2}'
    monetary_matches = list(re.finditer(monetary_pattern, line))
    
    if not monetary_matches:
        # Linha sem valores monetários - pode ser categoria
        if len(line) > 10:
            cleaned_account = clean_account_name(line)
            if cleaned_account:
                return {
                    "code": None,
                    "classification": None,
                    "account": cleaned_account,
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

def extract_data_from_pdf(pdf_path: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Extrai dados do PDF"""
    header = {}
    all_data = []
    parent_categories = []  # Stack de categorias pai
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            # Extrair texto para cabeçalho
            text = page.extract_text()
            if not text:
                continue
            
            # Extrair cabeçalho apenas da primeira página
            if page_num == 1:
                header = extract_header_info(text)
            
            # Reconstruir texto a partir de caracteres
            chars = page.chars
            reconstructed_lines = reconstruct_text_from_chars(chars, separate_bold=True)
            
            # Processar linhas reconstruídas
            for line_text, y_pos, is_bold in reconstructed_lines:
                if not line_text or len(line_text.strip()) < 3:
                    continue
                
                # Pular linhas de cabeçalho
                skip_keywords = [
                    'EMPRESA:', 'C.N.P.J.:', 'PERÍODO:', 'EMISSÃO:', 'HORA:', 
                    'BALANCETE', 'CÓDIGO', 'CLASSIFICAÇÃO', 'DESCRIÇÃO', 
                    'SALDO ANTERIOR', 'DÉBITO', 'CRÉDITO', 'SALDO ATUAL',
                    'CONSOLIDADO', 'CPF:', '_______________________________________',
                    'GILMIER', 'CRISTIANI', 'MIRI', 'ZUCOLOTO', 'NÚMERO LIVRO', 'FOLHA:'
                ]
                
                if any(keyword in line_text.upper() for keyword in skip_keywords):
                    continue
                
                # Verificar se é uma categoria principal (texto em negrito e sem classificação específica)
                if is_bold:
                    # Verificar se não tem classificação específica (formato X.X.XX.XXX.XX)
                    if not re.search(r'\d+\.\d+\.\d+\.\d+\.\d+', line_text):
                        # É uma categoria principal
                        cleaned_category = clean_account_name(line_text)
                        if cleaned_category and len(cleaned_category) > 5:
                            # Atualizar stack de categorias
                            # Remover categorias mais específicas se esta for mais geral
                            parent_categories = [c for c in parent_categories if not cleaned_category.upper().startswith(c.upper())]
                            parent_categories.append(cleaned_category)
                            
                            # Criar entrada para a categoria
                            entry = parse_data_line(line_text, is_bold=True)
                            if entry:
                                entry['parent_category'] = None
                                all_data.append(entry)
                            continue
                
                # Parse linha normal
                entry = parse_data_line(line_text, is_bold=False)
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
