#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pdfplumber
import json
import re
from typing import Dict, List, Any, Optional

def inspect_pdf(pdf_path: str):
    """Inspeciona a estrutura do PDF para entender melhor o formato"""
    with pdfplumber.open(pdf_path) as pdf:
        print(f"Total de páginas: {len(pdf.pages)}\n")
        
        for page_num, page in enumerate(pdf.pages, 1):
            print(f"\n{'='*80}")
            print(f"PÁGINA {page_num}")
            print(f"{'='*80}\n")
            
            # Extrair texto
            text = page.extract_text()
            if text:
                print("TEXTO EXTRAÍDO:")
                print(text[:2000])
                print("\n...\n")
            
            # Extrair tabelas
            tables = page.extract_tables()
            print(f"\nNúmero de tabelas encontradas: {len(tables)}\n")
            
            for i, table in enumerate(tables):
                if table:
                    print(f"Tabela {i+1} ({len(table)} linhas x {len(table[0]) if table else 0} colunas):")
                    # Mostrar primeiras linhas
                    for row_idx, row in enumerate(table[:10]):
                        print(f"  Linha {row_idx}: {row}")
                    if len(table) > 10:
                        print(f"  ... ({len(table) - 10} linhas restantes)")
                    print()
            
            # Analisar caracteres para identificar texto em negrito
            chars = page.chars
            if chars:
                print(f"\nTotal de caracteres: {len(chars)}")
                # Verificar fontes diferentes
                fonts = set()
                for char in chars[:100]:
                    font = char.get('fontname', 'unknown')
                    fonts.add(font)
                print(f"Fontes encontradas: {fonts}")
                
                # Mostrar alguns caracteres em negrito
                bold_chars = [c for c in chars if c.get('fontname', '').upper().find('BOLD') != -1 or c.get('bold', False)]
                if bold_chars:
                    print(f"\nCaracteres em negrito encontrados: {len(bold_chars)}")
                    # Agrupar caracteres em negrito consecutivos
                    bold_text = ""
                    for char in bold_chars[:50]:
                        bold_text += char.get('text', '')
                    print(f"Exemplo de texto em negrito: {bold_text[:200]}")

if __name__ == "__main__":
    inspect_pdf("/workspace/balancete.pdf")
