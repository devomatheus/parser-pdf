#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pdfplumber
import json
import re
from typing import Dict, List, Any, Optional, Tuple

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
    
    # Extrair nome da empresa (primeira linha geralmente)
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

def parse_line(line: str, bold_categories: Dict[int, str] = None) -> Optional[Dict[str, Any]]:
    """Parse uma linha de dados do balancete"""
    if not line or len(line.strip()) < 5:
        return None
    
    line = line.strip()
    
    # Padrão: código (opcional) | classificação | descrição | valores monetários
    # Valores monetários: podem ter formato X.XXX,XX ou X,XX
    
    # Tentar identificar valores monetários primeiro
    # Padrão: número com vírgula e 2 decimais, pode ter pontos como separador de milhar
    monetary_pattern = r'[\d\.]+,\d{2}|[\d]+,\d{2}'
    monetary_values = re.findall(monetary_pattern, line)
    
    # Se não encontrou valores monetários, pode ser uma linha de categoria
    if not monetary_values:
        # Verificar se é uma linha de categoria (texto em negrito ou sem valores)
        if len(line) > 20 and not re.search(r'\d{4,}', line):
            return {
                "code": None,
                "classification": None,
                "account": line.strip(),
                "previous_balance": None,
                "current_balance": None,
                "debit": None,
                "credit": None,
                "parent_category": None
            }
        return None
    
    # Separar a linha em partes
    # Tentar dividir por múltiplos espaços
    parts = re.split(r'\s{2,}', line)
    
    # Se não funcionou, tentar dividir por espaços simples mas preservando valores monetários
    if len(parts) < 3:
        # Estratégia: encontrar valores monetários e dividir o resto
        parts = []
        remaining = line
        
        # Encontrar posições dos valores monetários
        for match in re.finditer(monetary_pattern, remaining):
            before = remaining[:match.start()].strip()
            if before:
                parts.extend(before.split())
            parts.append(match.group())
            remaining = remaining[match.end():]
        
        if remaining.strip():
            parts.extend(remaining.strip().split())
    
    # Limpar partes vazias
    parts = [p.strip() for p in parts if p.strip()]
    
    if len(parts) < 3:
        return None
    
    # Identificar componentes
    code = None
    classification = None
    account = None
    previous_balance = None
    current_balance = None
    debit = None
    credit = None
    
    # Procurar classificação (formato X.X.XX.XXX.XX)
    classification_idx = -1
    for i, part in enumerate(parts):
        if re.match(r'^\d+\.\d+\.\d+\.\d+\.\d+$', part):
            classification = part
            classification_idx = i
            break
    
    # Procurar código simples (4-6 dígitos, não classificação)
    if classification_idx == -1:
        for i, part in enumerate(parts):
            if re.match(r'^\d{4,6}$', part) and not re.match(r'^\d+\.\d+', part):
                code = part
                break
    else:
        # Código geralmente vem antes da classificação
        if classification_idx > 0:
            potential_code = parts[classification_idx - 1]
            if re.match(r'^\d{4,6}$', potential_code):
                code = potential_code
    
    # Encontrar valores monetários
    monetary_indices = []
    for i, part in enumerate(parts):
        if re.match(monetary_pattern, part):
            monetary_indices.append(i)
    
    # Determinar qual valor é qual baseado na posição
    # Ordem esperada: Saldo Anterior, Débito, Crédito, Saldo Atual
    if len(monetary_indices) >= 4:
        previous_balance = parts[monetary_indices[0]]
        debit = parts[monetary_indices[1]]
        credit = parts[monetary_indices[2]]
        current_balance = parts[monetary_indices[3]]
    elif len(monetary_indices) == 3:
        previous_balance = parts[monetary_indices[0]]
        debit = parts[monetary_indices[1]]
        credit = parts[monetary_indices[2]]
    elif len(monetary_indices) == 2:
        previous_balance = parts[monetary_indices[0]]
        current_balance = parts[monetary_indices[1]]
    
    # Encontrar nome da conta (texto entre código/classificação e valores)
    start_idx = 0
    if code:
        for i, part in enumerate(parts):
            if part == code:
                start_idx = i + 1
                break
    elif classification:
        for i, part in enumerate(parts):
            if part == classification:
                start_idx = i + 1
                break
    
    end_idx = len(parts)
    if monetary_indices:
        end_idx = monetary_indices[0]
    
    account_parts = parts[start_idx:end_idx]
    account = ' '.join(account_parts).strip()
    
    if not account:
        return None
    
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

def extract_bold_text_by_position(chars: List[Dict]) -> Dict[int, str]:
    """Extrai texto em negrito agrupado por posição Y (linha)"""
    bold_texts = {}
    current_bold = ""
    current_y = None
    
    for char in chars:
        is_bold = char.get('fontname', '').upper().find('BOLD') != -1 or char.get('bold', False)
        char_y = char.get('top', 0)
        
        if is_bold:
            # Agrupar caracteres na mesma linha (tolerância de 2 pixels)
            if current_y is None or abs(char_y - current_y) < 2:
                current_bold += char.get('text', '')
                current_y = char_y
            else:
                # Nova linha
                if current_bold.strip() and len(current_bold.strip()) > 3:
                    y_key = int(current_y) if current_y else 0
                    if y_key not in bold_texts or len(current_bold.strip()) > len(bold_texts[y_key]):
                        bold_texts[y_key] = current_bold.strip()
                current_bold = char.get('text', '')
                current_y = char_y
        else:
            if current_bold.strip():
                y_key = int(current_y) if current_y else 0
                if y_key not in bold_texts or len(current_bold.strip()) > len(bold_texts[y_key]):
                    bold_texts[y_key] = current_bold.strip()
                current_bold = ""
                current_y = None
    
    if current_bold.strip():
        y_key = int(current_y) if current_y else 0
        if y_key not in bold_texts or len(current_bold.strip()) > len(bold_texts[y_key]):
            bold_texts[y_key] = current_bold.strip()
    
    return bold_texts

def extract_data_from_pdf(pdf_path: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Extrai dados do PDF"""
    header = {}
    all_data = []
    current_parent_category = None
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            # Extrair texto
            text = page.extract_text()
            if not text:
                continue
            
            # Extrair cabeçalho apenas da primeira página
            if page_num == 1:
                header = extract_header_info(text)
            
            # Extrair texto em negrito por posição
            chars = page.chars
            bold_texts_by_y = extract_bold_text_by_position(chars)
            
            # Criar mapeamento de Y para texto em negrito
            y_to_bold = {}
            for y, bold_text in bold_texts_by_y.items():
                # Normalizar Y para linha aproximada (arredondar para múltiplos de 10)
                y_normalized = (y // 10) * 10
                if y_normalized not in y_to_bold or len(bold_text) > len(y_to_bold[y_normalized]):
                    y_to_bold[y_normalized] = bold_text
            
            # Processar linhas de texto
            lines = text.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line or len(line) < 5:
                    continue
                
                # Pular linhas de cabeçalho
                if any(keyword in line.upper() for keyword in ['EMPRESA:', 'C.N.P.J.:', 'PERÍODO:', 'EMISSÃO:', 'HORA:', 'BALANCETE', 'CÓDIGO', 'CLASSIFICAÇÃO', 'DESCRIÇÃO', 'SALDO ANTERIOR', 'DÉBITO', 'CRÉDITO', 'SALDO ATUAL']):
                    continue
                
                # Verificar se a linha contém texto em negrito (categoria principal)
                line_y = None
                for char in chars:
                    if char.get('text', '') and char.get('text', '')[0] == line[0] if line else False:
                        line_y = char.get('top', 0)
                        break
                
                if line_y is not None:
                    y_normalized = (int(line_y) // 10) * 10
                    if y_normalized in y_to_bold:
                        bold_text = y_to_bold[y_normalized]
                        # Verificar se o texto em negrito está na linha
                        if bold_text.upper() in line.upper() or line.upper().startswith(bold_text.upper()[:20]):
                            # É uma categoria principal
                            current_parent_category = bold_text.strip()
                            # Também criar entrada para a categoria
                            entry = parse_line(line)
                            if entry:
                                entry['parent_category'] = None  # Categoria principal não tem parent
                                all_data.append(entry)
                            continue
                
                # Parse linha normal
                entry = parse_line(line)
                if entry:
                    # Associar categoria pai se existir
                    if current_parent_category:
                        entry['parent_category'] = current_parent_category
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
