#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script para limpar registros do MongoDB com bairro vazio
Usage: python cleanup_empty_bairro.py [--execute]
"""
import sys
from database import MongoDB

def main():
    # Verificar se deve executar ou apenas simular
    execute = '--execute' in sys.argv
    
    print("=== Cleanup de Registros com Bairro Vazio ===")
    
    # Conectar ao banco
    db = MongoDB()
    
    if execute:
        print("MODO DE EXECUÇÃO: Registros serão deletados")
        result = db.cleanup_empty_bairro_records(dry_run=False)
    else:
        print("MODO DE SIMULAÇÃO: Use --execute para deletar de fato")
        result = db.cleanup_empty_bairro_records(dry_run=True)
    
    print("\nResultado:")
    print("- Registros encontrados: {}".format(result['count']))
    print("- Status: {}".format(result['message']))
    
    if result['count'] > 0:
        print("\nCEPs afetados:")
        for cep in result['ceps'][:10]:  # Mostrar apenas os primeiros 10
            print("  - {}".format(cep))
        
        if len(result['ceps']) > 10:
            print("  ... e mais {} CEPs".format(len(result['ceps']) - 10))
    
    print("\nRegistros foram deletados: {}".format('Sim' if result.get('deleted') else 'Não'))

if __name__ == '__main__':
    main()